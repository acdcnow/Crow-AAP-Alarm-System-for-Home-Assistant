"""Crow/AAP Alarm IP Module TCP client.

Threaded, blocking-socket transport (safe to run in a Home Assistant executor
thread) that speaks the Crow/AAP line protocol. Command wire-formats and the
RX line parser mirror the reference pycrowipmodule library, driven by the
COMMANDS and RESPONSE_FORMATS tables in crow_defs.py.

Two behaviours here exist purely to keep Home Assistant quiet:

* a state line that reports a value the panel already has is not dispatched at
  all, so the full status dump a ``STATUS`` probe provokes does not rewrite every
  entity, and
* the connection state is announced only when it really changes, and a blip that
  heals within one reconnect is not announced at all.
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

# How long a link has to have held before a drop is treated as a network blip
# that is worth one immediate retry. A link that flaps faster than this is a real
# failure and goes through the backoff instead, which is what stops a panel that
# accepts and immediately drops from being hammered.
_STABLE_CONNECTION = 5.0

# Whatever the config entry carries, the keep-alive is clamped into this range.
# Below the lower bound the driver would probe on every read timeout, above the
# upper bound it would not keep anything alive.
_MIN_KEEPALIVE = 15.0
_MAX_KEEPALIVE = 3600.0

# The area state flags that exclude each other: an area message sets exactly one
# of them and clears the rest, so all five take part in "did anything change?".
_AREA_FLAGS = ("armed", "stay_armed", "disarmed", "exit_delay", "stay_exit_delay")


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
            if panel_keepalive is not None:
                self.keepalive = float(panel_keepalive)

        if not self.host:
            self.host = "127.0.0.1"
        if not self.port:
            self.port = 5002

        # A keep-alive outside this range cannot work, whatever the entry says.
        self.keepalive = max(_MIN_KEEPALIVE, min(float(self.keepalive), _MAX_KEEPALIVE))

        self._socket = None
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self._is_connected = False
        #: The connection state the caller was last told about. Notifications are
        #: only emitted when this changes, so a drop and a quick reconnect cannot
        #: flip every entity to "unavailable" and back for nothing.
        self._reported_connected = False
        self._running = False
        self._thread = None
        self._wakeup = threading.Event()

        self._base_reconnect_delay = 10
        self._reconnect_delay = self._base_reconnect_delay
        self._max_reconnect_delay = 60
        self._stable_connection = _STABLE_CONNECTION

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
        self._is_connected = False
        self._wakeup.set()
        self._close_socket()

    def _run_loop(self):
        """Supervised connect/listen/reconnect loop with exponential backoff.

        A dropped link is not announced immediately. A connection that had been
        up for a while is retried once, straight away; if that retry succeeds the
        outage never happened as far as Home Assistant is concerned. Only when it
        keeps failing is the disconnect reported and the backoff started.
        """
        while self._running:
            attempt_started = time.monotonic()
            connected = self._connect()
            if connected:
                self._notify_connection(True)
                self._reconnect_delay = self._base_reconnect_delay
                # Give the module a moment, then pull a full status dump.
                self.request_status()
                self._listen_loop()

            if not self._running:
                break

            self._is_connected = False
            self._close_socket()

            uptime = time.monotonic() - attempt_started
            if connected and uptime >= self._stable_connection:
                # The link was healthy: absorb the blip by reconnecting at once.
                _LOGGER.debug(
                    "Connection to %s:%s dropped after %.1fs - retrying immediately.",
                    self.host,
                    self.port,
                    uptime,
                )
                continue

            self._notify_connection(False)

            delay = self._reconnect_delay
            _LOGGER.info("Reconnecting to Crow IP Module in %d seconds...", delay)
            self._wakeup.wait(delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

        _LOGGER.debug("Crow IP client worker loop exited.")

    def _connect(self) -> bool:
        """Open the TCP connection. Returns True on success.

        This does not touch the connection state the caller sees; the supervisor
        decides whether a transition is announced (see ``_run_loop``).
        """
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
        """The raw socket state - True only while a socket is known to work."""
        return self._is_connected

    @property
    def connected(self) -> bool:
        """The connection state most recently reported to the caller.

        Unlike :attr:`is_connected` this does not dip while a dropped link is
        being retried, which is what entity availability follows.
        """
        return self._reported_connected

    # ------------------------------------------------------------------ #
    # Connection-state notifications (drive HA availability / refresh)
    # ------------------------------------------------------------------ #
    def _notify_connection(self, connected: bool):
        """Announce a connection transition - at most once per state.

        Home Assistant is only told when the state really changes. A module that
        drops and is back a second later therefore produces no ``unavailable`` /
        ``available`` pair, and a repeated report is not forwarded twice.
        """
        connected = bool(connected)
        with self._state_lock:
            if connected == self._reported_connected:
                return
            self._reported_connected = connected
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
        """Parse one line, update panel state, and invoke the HA callback.

        A line that reports a state the panel already has is dropped here. The
        module repeats its entire status after every ``STATUS`` probe, and
        forwarding those repeats would rewrite every affected entity - and every
        recorder row - for nothing. A handler returns ``None`` for "no change".
        """
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
        if result is None:
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
        status = self.panel.system_state["status"]
        attribute = msg["attribute"]
        if status.get(attribute) == msg["status"]:
            return None
        _LOGGER.debug("System state %s -> %s", msg["name"], msg["status"])
        status[attribute] = msg["status"]
        return attribute

    def handle_output_state_change(self, msg):
        output_number = msg["data"]
        state = self.panel.output_state.get(int(output_number))
        if state is None:
            return None
        status = state["status"]
        attribute = msg["attribute"]
        if status.get(attribute) == msg["status"]:
            return None
        _LOGGER.debug("Output state %s -> %s", msg["name"], msg["status"])
        status[attribute] = msg["status"]
        return output_number

    def handle_area_state_change(self, msg):
        area_idx = int(msg["area"])
        area_label = "A" if area_idx == 1 else "B"
        status = self.panel.area_state[area_idx]["status"]

        before = (
            tuple(status.get(flag, False) for flag in _AREA_FLAGS),
            status.get("alarm", False),
            status.get("alarm_zone", ""),
        )

        # A new area state message is exclusive: clear the others first.
        for flag in _AREA_FLAGS:
            status[flag] = False
        status[msg["attribute"]] = msg["status"]

        if status["disarmed"]:
            status["alarm"] = False
            status["alarm_zone"] = ""

        after = (
            tuple(status.get(flag, False) for flag in _AREA_FLAGS),
            status.get("alarm", False),
            status.get("alarm_zone", ""),
        )
        if before == after:
            return None

        _LOGGER.debug("Area %s state %s -> %s", area_label, msg["name"], msg["status"])
        return area_label

    def handle_zone_state_change(self, msg):
        zone_number = msg["data"]
        state = self.panel.zone_state.get(int(zone_number))
        if state is None:
            return None
        status = state["status"]
        attribute = msg["attribute"]
        if status.get(attribute) == msg["status"]:
            return None

        _LOGGER.debug("Zone %s state %s -> %s", zone_number, msg["name"], msg["status"])
        status[attribute] = msg["status"]

        if attribute == "alarm":
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
