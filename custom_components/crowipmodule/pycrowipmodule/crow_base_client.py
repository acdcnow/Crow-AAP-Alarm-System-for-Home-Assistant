"""Crow/AAP Alarm IP Module TCP client.

Threaded, blocking-socket transport (safe to run in a Home Assistant executor
thread) that speaks the Crow/AAP line protocol. Command wire-formats and the
RX line parser mirror the reference pycrowipmodule library, driven by the
COMMANDS and RESPONSE_FORMATS tables in crow_defs.py.
"""
import logging
import re
import socket
import threading
import time

from .crow_defs import COMMANDS, RESPONSE_FORMATS

_LOGGER = logging.getLogger(__name__)

# Socket read timeout during the listen loop. Kept short (independent of the
# connection timeout) so the loop wakes regularly to service keep-alive and to
# notice a requested shutdown promptly.
_RECV_TIMEOUT = 5.0


class CrowIPModuleClient:
    """Thread-safe client for the Crow IP Module with reconnect and keep-alive."""

    def __init__(self, *args, **kwargs):
        self.panel = None
        self.host = None
        self.port = None
        self.timeout = 10.0
        self.keepalive = 300.0

        # Positional: (panel, loop) from CrowIPAlarmPanel, or (host, port).
        if args:
            if not isinstance(args[0], str):
                self.panel = args[0]
                if len(args) > 1 and isinstance(args[1], (int, float)):
                    self.port = int(args[1])
            else:
                self.host = str(args[0])
                if len(args) > 1 and args[1] is not None:
                    self.port = int(args[1])

        if kwargs.get("panel") is not None:
            self.panel = kwargs["panel"]
        if kwargs.get("host") is not None:
            self.host = str(kwargs["host"])
        elif kwargs.get("ip") is not None:
            self.host = str(kwargs["ip"])
        if kwargs.get("port") is not None:
            self.port = int(kwargs["port"])
        if kwargs.get("timeout") is not None:
            self.timeout = float(kwargs["timeout"])
        if kwargs.get("keepalive") is not None:
            self.keepalive = float(kwargs["keepalive"])

        # Pull connection details straight off the panel object when present.
        if self.panel is not None:
            if not self.host:
                self.host = str(getattr(self.panel, "host", "") or getattr(self.panel, "_host", "") or "")
            if not self.port:
                self.port = int(getattr(self.panel, "port", 0) or getattr(self.panel, "_port", 0) or 0)
            panel_timeout = getattr(self.panel, "connection_timeout", None)
            if panel_timeout:
                self.timeout = float(panel_timeout)
            panel_keepalive = getattr(self.panel, "keepalive_interval", None)
            if panel_keepalive:
                self.keepalive = float(panel_keepalive)

        if not self.host:
            self.host = "127.0.0.1"
        if not self.port:
            self.port = 5002

        self._socket = None
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self._is_connected = False
        self._running = False
        self._thread = None
        self._wakeup = threading.Event()

        self._base_reconnect_delay = 10
        self._reconnect_delay = self._base_reconnect_delay
        self._max_reconnect_delay = 60

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self):
        """Start the background worker thread (idempotent)."""
        with self._state_lock:
            if self._running and self._thread and self._thread.is_alive():
                _LOGGER.debug("Client worker thread already running.")
                return
            self._running = True
            self._wakeup.clear()
            self._thread = threading.Thread(
                target=self._run_loop, name="CrowIPClientThread", daemon=True
            )
            self._thread.start()

    def stop(self):
        """Stop the worker thread and close the socket."""
        _LOGGER.debug("Stop requested for Crow IP client.")
        self._running = False
        self._wakeup.set()
        self._close_socket()

    def _run_loop(self):
        """Supervised connect/listen/reconnect loop with exponential backoff."""
        while self._running:
            connected = self._connect()
            if connected:
                self._reconnect_delay = self._base_reconnect_delay
                # Give the module a moment, then pull a full status dump.
                self.request_status()
                self._listen_loop()

            if not self._running:
                break

            delay = self._reconnect_delay
            _LOGGER.info("Reconnecting to Crow IP Module in %d seconds...", delay)
            self._wakeup.wait(delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

        _LOGGER.debug("Crow IP client worker loop exited.")

    def _connect(self) -> bool:
        """Open the TCP connection. Returns True on success."""
        self._close_socket()
        try:
            _LOGGER.info("Connecting to Crow IP Module at %s:%s", self.host, self.port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            # Shorten timeout for the read loop so it services keep-alive/shutdown.
            sock.settimeout(_RECV_TIMEOUT)
            self._socket = sock
            self._is_connected = True
            _LOGGER.info("Connected to Crow IP Module at %s:%s.", self.host, self.port)
            self._notify_connection(True)
            return True
        except (OSError, socket.timeout) as err:
            _LOGGER.warning("Failed to connect to Crow IP Module (%s:%s): %s", self.host, self.port, err)
            self._is_connected = False
            self._close_socket()
            self._notify_login_timeout()
            return False

    def _listen_loop(self):
        """Read and dispatch lines until the connection drops or we stop."""
        buffer = ""
        last_keepalive = time.monotonic()
        while self._running and self._is_connected and self._socket is not None:
            try:
                data = self._socket.recv(1024)
                if not data:
                    _LOGGER.warning("Crow IP Module closed the connection.")
                    break

                buffer += data.decode("ascii", errors="ignore")
                while "\r\n" in buffer or "\n" in buffer:
                    sep = "\r\n" if "\r\n" in buffer else "\n"
                    line, buffer = buffer.split(sep, 1)
                    line = line.strip()
                    if line:
                        _LOGGER.debug("RX: %s", line)
                        self._dispatch_line(line)

            except socket.timeout:
                # Idle tick: send keep-alive STATUS if the interval elapsed.
                if time.monotonic() - last_keepalive >= self.keepalive:
                    if self.request_status():
                        last_keepalive = time.monotonic()
                continue
            except (OSError, socket.error) as err:
                if self._running:
                    _LOGGER.warning("Socket read error: %s", err)
                break
            except Exception as err:  # noqa: BLE001 - never let the thread die silently
                _LOGGER.exception("Unexpected error in Crow read loop: %s", err)
                break

        self._is_connected = False
        self._close_socket()
        self._notify_connection(False)

    def _close_socket(self):
        """Close the socket, ignoring teardown errors."""
        sock = self._socket
        self._socket = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    # ------------------------------------------------------------------ #
    # Connection-state notifications (drive HA availability / refresh)
    # ------------------------------------------------------------------ #
    def _notify_connection(self, connected: bool):
        cb = getattr(self.panel, "callback_connected", None) if self.panel else None
        if callable(cb):
            try:
                cb(connected)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Error in connected callback: %s", err)

    def _notify_login_timeout(self):
        cb = getattr(self.panel, "callback_login_timeout", None) if self.panel else None
        if callable(cb):
            try:
                cb(False)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Error in login-timeout callback: %s", err)

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #
    def send_data(self, data: str) -> bool:
        """Send a raw string, appending the CR/LF terminator."""
        if not self._is_connected or self._socket is None:
            _LOGGER.warning("Cannot send '%s': not connected.", data)
            return False
        payload = (data + "\r\n").encode("ascii")
        try:
            with self._send_lock:
                self._socket.sendall(payload)
            _LOGGER.debug("TX: %s", payload)
            return True
        except (OSError, socket.error) as err:
            _LOGGER.error("Failed to send '%s': %s. Dropping connection.", data, err)
            self._is_connected = False
            self._close_socket()
            return False

    def send_command(self, code: str, data: str = "") -> bool:
        """Format a command per the Crow protocol and send it.

        `code` is a key in COMMANDS. Empty data yields "<CMD> "; the OO output
        command concatenates its argument with no space ("OO1"); everything
        else uses "<CMD> <data>".
        """
        if code not in COMMANDS:
            _LOGGER.error("Unknown command key: %s", code)
            return False
        cmd = COMMANDS[code]
        if data == "":
            to_send = cmd + " "
        elif cmd == "OO":
            to_send = cmd + data
        else:
            to_send = cmd + " " + data
        return self.send_data(to_send)

    def request_status(self) -> bool:
        """Ask the panel for a full status dump (also used as keep-alive)."""
        return self.send_command("status", "")

    # ------------------------------------------------------------------ #
    # Public commands (called by CrowIPAlarmPanel)
    # ------------------------------------------------------------------ #
    def arm_stay(self):
        self.send_command("stay", "")

    def arm_away(self):
        self.send_command("arm", "")

    def disarm(self, code):
        self.send_command("disarm", str(code) + "E")
        self.request_status()

    def send_keys(self, keys):
        self.send_command("keys", str(keys) + "E")

    def panic_alarm(self, panic_type):
        self.send_command("panic", "")

    def toggle_output(self, output_number):
        self.send_command("toogle_output_x", str(output_number))

    def toggle_chime(self):
        self.send_command("toggle_chime", "")

    def activate_relay(self, relay_no):
        if int(relay_no) == 1:
            self.send_command("relay_1_on", "")
        else:
            self.send_command("relay_2_on", "")

    # ------------------------------------------------------------------ #
    # Receiving / parsing
    # ------------------------------------------------------------------ #
    def _dispatch_line(self, line: str):
        """Parse one line, update panel state, and invoke the HA callback."""
        parsed = self._parse_line(line)
        if not parsed:
            return

        result = None
        handler = getattr(self, parsed.get("handler", ""), None)
        if callable(handler):
            try:
                result = handler(parsed)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Error in handler %s: %s", parsed.get("handler"), err)
                return

        callback = getattr(self.panel, parsed.get("callback", ""), None) if self.panel else None
        if callable(callback):
            try:
                callback(result)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Error in callback %s: %s", parsed.get("callback"), err)

    def _parse_line(self, raw: str) -> dict:
        """Match a line against RESPONSE_FORMATS and build a parsed record."""
        result = {}
        if not raw:
            return result
        for pattern, fmt in RESPONSE_FORMATS.items():
            match = re.match(pattern, raw)
            if not match:
                continue
            result["attribute"] = fmt["attr"]
            result["name"] = fmt["name"]
            result["status"] = fmt["status"]
            result["handler"] = "handle_%s" % fmt["handler"]
            result["callback"] = "callback_%s" % fmt["handler"]
            if fmt["handler"] == "area_state_change":
                result["area"] = fmt["area"]
            result["data"] = match.group("data") if match.groupdict().get("data") else ""
            break
        return result

    def handle_system_state_change(self, msg):
        _LOGGER.debug("System state %s -> %s", msg["name"], msg["status"])
        self.panel.system_state["status"][msg["attribute"]] = msg["status"]
        return msg["attribute"]

    def handle_output_state_change(self, msg):
        _LOGGER.debug("Output state %s -> %s", msg["name"], msg["status"])
        output_number = msg["data"]
        idx = int(output_number)
        if idx in self.panel.output_state:
            self.panel.output_state[idx]["status"][msg["attribute"]] = msg["status"]
        return output_number

    def handle_area_state_change(self, msg):
        _LOGGER.debug("Area state %s -> %s", msg["name"], msg["status"])
        area_idx = int(msg["area"])
        area_label = "A" if area_idx == 1 else "B"
        status = self.panel.area_state[area_idx]["status"]

        # A new area state message is exclusive: clear the others first.
        status["armed"] = False
        status["stay_armed"] = False
        status["disarmed"] = False
        status["exit_delay"] = False
        status["stay_exit_delay"] = False
        status[msg["attribute"]] = msg["status"]

        if status["disarmed"]:
            status["alarm"] = False
            status["alarm_zone"] = ""

        return area_label

    def handle_zone_state_change(self, msg):
        _LOGGER.debug("Zone %s state %s -> %s", msg["data"], msg["name"], msg["status"])
        zone_number = msg["data"]
        idx = int(zone_number)
        if idx in self.panel.zone_state:
            self.panel.zone_state[idx]["status"][msg["attribute"]] = msg["status"]

        if msg["attribute"] == "alarm":
            for area_idx in self.panel.area_state:
                area_status = self.panel.area_state[area_idx]["status"]
                if msg["status"]:
                    area_status["alarm"] = True
                    area_status["alarm_zone"] = zone_number
                else:
                    area_status["alarm"] = False
                    area_status["alarm_zone"] = ""
            # Refresh alarm panel entities as well as the zone sensor.
            for label in ("A", "B"):
                cb = getattr(self.panel, "callback_area_state_change", None)
                if callable(cb):
                    try:
                        cb(label)
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.error("Error invoking area callback: %s", err)

        return zone_number
