"""Standalone self-test for the Crow IP Module protocol layer.

Runs WITHOUT Home Assistant installed: it imports only the bundled
`pycrowipmodule` library (which has no `homeassistant` dependency).

Usage (from the "sync check" folder, with a real Python interpreter):

    python test_crow_protocol.py

Exit code 0 = all tests passed, 1 = one or more failures.
"""
import os
import socket
import sys
import threading
import time

# Import the bundled library directly, as a top-level package, so we do NOT
# pull in custom_components/crowipmodule/__init__.py (which needs homeassistant).
LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "custom_components", "crowipmodule")
sys.path.insert(0, LIB_DIR)

from pycrowipmodule import CrowIPAlarmPanel, CrowIPModuleClient  # noqa: E402

_failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        _failures.append(label)


# --------------------------------------------------------------------------- #
# 1. Command wire-format tests
# --------------------------------------------------------------------------- #
def test_commands():
    print("\n== Command wire formats ==")
    panel = CrowIPAlarmPanel("127.0.0.1", 5002, "0000", 300, None, 5)
    client = CrowIPModuleClient(panel)

    sent = []
    client.send_data = lambda data: (sent.append(data) or True)

    client.arm_away()
    check("arm_away -> 'ARM '", sent[-1] == "ARM ")

    client.arm_stay()
    check("arm_stay -> 'STAY '", sent[-1] == "STAY ")

    client.panic_alarm("")
    check("panic_alarm -> 'PANIC '", sent[-1] == "PANIC ")

    client.toggle_chime()
    check("toggle_chime -> 'CHIME '", sent[-1] == "CHIME ")

    client.toggle_output("2")
    check("toggle_output(2) -> 'OO2' (no space)", sent[-1] == "OO2")

    client.activate_relay(1)
    check("activate_relay(1) -> 'RL1 '", sent[-1] == "RL1 ")

    client.activate_relay(2)
    check("activate_relay(2) -> 'RL2 '", sent[-1] == "RL2 ")

    client.send_keys("12")
    check("send_keys('12') -> 'KEYS 12E'", sent[-1] == "KEYS 12E")

    sent.clear()
    client.disarm("1234")
    check("disarm('1234') sends 'KEYS 1234E' then 'STATUS '",
          sent == ["KEYS 1234E", "STATUS "])


# --------------------------------------------------------------------------- #
# 2. Parser + state-handler tests (no sockets)
# --------------------------------------------------------------------------- #
def test_parsing():
    print("\n== RX parsing + state handlers ==")
    panel = CrowIPAlarmPanel("127.0.0.1", 5002, "0000", 300, None, 5)
    client = CrowIPModuleClient(panel)

    client._dispatch_line("ZO1")
    check("ZO1 opens zone 1", panel.zone_state[1]["status"]["open"] is True)

    client._dispatch_line("ZC1")
    check("ZC1 closes zone 1", panel.zone_state[1]["status"]["open"] is False)

    client._dispatch_line("ZA3")
    check("ZA3 raises zone 3 alarm", panel.zone_state[3]["status"]["alarm"] is True)
    check("ZA3 propagates area A alarm", panel.area_state[1]["status"]["alarm"] is True)
    check("ZA3 records alarm_zone '3'", panel.area_state[1]["status"]["alarm_zone"] == "3")

    client._dispatch_line("ZR3")
    check("ZR3 restores zone 3 alarm", panel.zone_state[3]["status"]["alarm"] is False)
    check("ZR3 clears area alarm", panel.area_state[1]["status"]["alarm"] is False)

    client._dispatch_line("AA")
    check("AA arms area A (armed)", panel.area_state[1]["status"]["armed"] is True)
    check("AA leaves disarmed False", panel.area_state[1]["status"]["disarmed"] is False)

    client._dispatch_line("DA")
    check("DA disarms area A", panel.area_state[1]["status"]["disarmed"] is True)
    check("DA clears armed flag", panel.area_state[1]["status"]["armed"] is False)

    client._dispatch_line("SB")
    check("SB stay-arms area B", panel.area_state[2]["status"]["stay_armed"] is True)

    client._dispatch_line("MF")
    check("MF sets mains fail", panel.system_state["status"]["mains"] is False)
    client._dispatch_line("MR")
    check("MR restores mains", panel.system_state["status"]["mains"] is True)

    client._dispatch_line("BF")
    check("BF sets battery fail", panel.system_state["status"]["battery"] is False)

    client._dispatch_line("OO2")
    check("OO2 turns output 2 on", panel.output_state[2]["status"]["open"] is True)
    client._dispatch_line("OC2")
    check("OC2 turns output 2 off", panel.output_state[2]["status"]["open"] is False)

    client._dispatch_line("ZBY5")
    check("ZBY5 bypasses zone 5", panel.zone_state[5]["status"]["bypass"] is True)
    client._dispatch_line("GARBAGE")
    check("Unknown line is ignored without error", True)


# --------------------------------------------------------------------------- #
# 3. End-to-end loopback test (real sockets + worker thread)
# --------------------------------------------------------------------------- #
def test_loopback():
    print("\n== Loopback end-to-end ==")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def serve():
        try:
            conn, _ = server.accept()
            conn.sendall(b"AA\r\nZO1\r\nMF\r\n")
            time.sleep(1.5)
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()

    panel = CrowIPAlarmPanel("127.0.0.1", port, "0000", 300, None, 5)
    connected = {"v": False}
    panel.callback_connected = lambda v: connected.__setitem__("v", bool(v))
    panel.start()

    # Wait up to 3s for state to propagate.
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if panel.zone_state[1]["status"]["open"] and panel.area_state[1]["status"]["armed"]:
            break
        time.sleep(0.05)

    check("loopback: connected callback fired", connected["v"] is True)
    check("loopback: area A armed via AA", panel.area_state[1]["status"]["armed"] is True)
    check("loopback: zone 1 open via ZO1", panel.zone_state[1]["status"]["open"] is True)
    check("loopback: mains fail via MF", panel.system_state["status"]["mains"] is False)
    check("loopback: is_connected True", panel.is_connected is True)

    panel.stop()
    server.close()
    time.sleep(0.3)
    check("loopback: is_connected False after stop", panel.is_connected is False)


if __name__ == "__main__":
    test_commands()
    test_parsing()
    test_loopback()

    print("\n" + "=" * 40)
    if _failures:
        print(f"{len(_failures)} FAILURE(S): {_failures}")
        sys.exit(1)
    print("ALL TESTS PASSED")
    sys.exit(0)
