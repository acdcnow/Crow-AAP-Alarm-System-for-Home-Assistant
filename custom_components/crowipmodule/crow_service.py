"""
Local implementation of the Crow/AAP IP Module logic.
"""
import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

class CrowIPAlarmPanel:
    """Controls the Crow/AAP IP Module via direct TCP connection."""

    def __init__(self, host, port, code, keepalive_interval, loop, timeout):
        self._host = host
        self._port = port
        self._code = code 
        self._keepalive_interval = keepalive_interval
        self._timeout = timeout
        
        self._reader = None
        self._writer = None
        self._running = False
        self._connect_task = None
        
        self.zone_state = {}     
        self.area_state = {
            1: {'status': {'armed': False, 'stay_armed': False, 'alarm': False, 'disarmed': True, 'exit_delay': False}},
            2: {'status': {'armed': False, 'stay_armed': False, 'alarm': False, 'disarmed': True, 'exit_delay': False}}
        }
        self.output_state = {}   
        self.system_state = {    
            "status": {
                "mains": True, "battery": True, "tamper": False
            }
        }

        self.callback_zone_state_change = None
        self.callback_area_state_change = None
        self.callback_system_state_change = None
        self.callback_output_state_change = None
        self.callback_connected = None
        self.callback_login_timeout = None

    def start(self):
        self._running = True
        self._connect_task = asyncio.create_task(self._connect_loop())

    async def _connect_loop(self):
        while self._running:
            try:
                _LOGGER.info(f"Connecting to {self._host}:{self._port}...")
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port), 
                    timeout=self._timeout
                )
                
                _LOGGER.info("Connected to Crow IP Module.")
                if self.callback_connected: self.callback_connected(True)

                await self.send_command("STATUS")
                await asyncio.sleep(0.5)

                while self._running:
                    try:
                        data = await asyncio.wait_for(self._reader.readuntil(b'\n'), timeout=self._keepalive_interval + 10)
                        line = data.decode('utf-8', errors='ignore').strip()
                        if line:
                            _LOGGER.debug(f"RX RAW: '{line}'")
                            self._parse_line(line)
                    except asyncio.TimeoutError:
                        await self.send_command("STATUS")
                    except Exception:
                        break

            except (OSError, asyncio.TimeoutError) as e:
                _LOGGER.warning(f"Connection failed: {e}. Retrying in 10s...")
                if self.callback_login_timeout: self.callback_login_timeout(False)
            
            await self._disconnect_internal()
            if self._running: await asyncio.sleep(10)

    async def _disconnect_internal(self):
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception: pass
            self._writer = None
            self._reader = None

    def stop(self):
        self._running = False
        if self._connect_task: self._connect_task.cancel()
        if self._writer:
            try: self._writer.close()
            except Exception: pass

    async def send_command(self, cmd):
        if self._writer:
            try:
                _LOGGER.debug(f"TX CMD: '{cmd}'")
                self._writer.write(f"{cmd}\r\n".encode())
                await self._writer.drain()
            except Exception as e:
                _LOGGER.error(f"TX Error: {e}")

    async def _send_sequence(self, commands):
        """Send commands sequentially with a delay."""
        for cmd in commands:
            if not self._running: break
            await self.send_command(str(cmd))
            await asyncio.sleep(0.5)

    # --- ACTIONS ---

    def disarm(self, code):
        """
        Sequence: CODE -> ENTER
        The 'Disarm' button in HA acts as the 'Enter' key here.
        """
        _LOGGER.info(f"Sending Disarm Sequence (Code + Enter)")
        asyncio.create_task(self._send_sequence([code, "E"]))

    def arm_away(self, code):
        """Sequence: CODE -> ARM -> ENTER"""
        c = code if code else self._code
        _LOGGER.info(f"Sending Arm Away Sequence")
        asyncio.create_task(self._send_sequence([c, "ARM", "E"]))

    def arm_stay(self, code):
        """Sequence: CODE -> STAY -> ENTER"""
        c = code if code else self._code
        _LOGGER.info(f"Sending Arm Stay Sequence")
        asyncio.create_task(self._send_sequence([c, "STAY", "E"]))

    def bypass(self, code):
        """Sequence: CODE -> BYPASS -> ENTER"""
        c = code if code else self._code
        _LOGGER.info(f"Sending Bypass Sequence")
        # Assuming 'BYPASS' is the command string, might be 'B' or 'MEM' depending on exact firmware
        # Standard AAP/Crow is often 'B' or 'BYPASS'
        asyncio.create_task(self._send_sequence([c, "BYPASS", "E"]))

    def send_keypress(self, key):
        asyncio.create_task(self.send_command(key))

    def command_output(self, output_index):
        asyncio.create_task(self.send_command(f"RL{output_index}"))

    def panic_alarm(self, panic_type):
        asyncio.create_task(self.send_command("PANIC"))

    # --- PARSING ---
    def _parse_line(self, line):
        line = line.upper()

        if line.startswith(("ZO", "ZC", "ZA")) or "ZONE" in line:
            self._parse_zone(line)

        elif line.startswith(("OO", "OF", "RL")):
            self._parse_output(line)
        
        elif "MAINS FAIL" in line or "POWER FAIL" in line:
            self.system_state['status']['mains'] = False
            self._notify_system()
        elif "MAINS" in line and ("OK" in line or "RESTORE" in line):
            self.system_state['status']['mains'] = True
            self._notify_system()
        elif "LOW BATT" in line:
            self.system_state['status']['battery'] = False
            self._notify_system()
        elif "BATT" in line and ("OK" in line or "RESTORE" in line):
             self.system_state['status']['battery'] = True
             self._notify_system()
        
        # Area Logic
        target_area = 2 if ("AREA B" in line or "AREA 2" in line or line.endswith(" B")) else 1
        
        # Enhanced Parsing for Panel Feedback
        if "ARMED" in line and "STAY" not in line:
             self._update_area(target_area, armed=True, stay=False, exit=False)
        elif line.startswith("AR"): 
             self._update_area(target_area, armed=True, stay=False, exit=False)
        
        elif "STAY" in line:
             self._update_area(target_area, armed=True, stay=True, exit=False)
        elif line.startswith("ST"):
             self._update_area(target_area, armed=True, stay=True, exit=False)
             
        elif "DISARMED" in line:
             self._update_area(target_area, armed=False, stay=False, exit=False)
        elif line.startswith("DA"):
             self._update_area(target_area, armed=False, stay=False, exit=False)
             
        elif "EXIT" in line or line.startswith("EX"):
             self._update_area(target_area, exit=True)
             
        elif "ALARM" in line:
            self._update_area(target_area, alarm=True)
        elif "RESTORE" in line:
            self._update_area(target_area, alarm=False)

    def _parse_zone(self, line):
        try:
            import re
            match = re.search(r'\d+', line)
            if match:
                zone_id = int(match.group())
                if zone_id not in self.zone_state:
                    self.zone_state[zone_id] = {'status': {'open': False, 'alarm': False, 'tamper': False}}
                
                status = self.zone_state[zone_id]['status']
                
                if "ZO" in line or "OPEN" in line or "ALARM" in line:
                    status['open'] = True
                if "ZC" in line or "CLOSE" in line or "OK" in line:
                    status['open'] = False
                if "ZA" in line or "ALARM" in line:
                    status['alarm'] = True
                    status['open'] = True 
                
                if self.callback_zone_state_change:
                    self.callback_zone_state_change(zone_id)
        except Exception: pass

    def _parse_output(self, line):
        try:
            import re
            match = re.search(r'\d+', line)
            if match:
                out_id = int(match.group())
                is_on = "OO" in line or "ON" in line
                if out_id not in self.output_state:
                    self.output_state[out_id] = {'status': {'open': False}}
                self.output_state[out_id]['status']['open'] = is_on
                if self.callback_output_state_change:
                    self.callback_output_state_change(out_id)
        except Exception: pass

    def _update_area(self, area_id, armed=None, stay=None, alarm=None, exit=None):
        if area_id not in self.area_state:
            self.area_state[area_id] = {'status': {'armed': False, 'stay_armed': False, 'alarm': False, 'disarmed': True, 'exit_delay': False}}
        
        status = self.area_state[area_id]['status']
        changed = False

        if armed is not None:
            if status['armed'] != armed: 
                status['armed'] = armed
                changed = True
            if status['disarmed'] != (not armed):
                status['disarmed'] = not armed
                changed = True
        
        if stay is not None:
            if status['stay_armed'] != stay:
                status['stay_armed'] = stay
                changed = True
            if stay and status['armed']: 
                status['armed'] = False
                changed = True

        if exit is not None:
            if status['exit_delay'] != exit:
                status['exit_delay'] = exit
                changed = True

        if alarm is not None:
            if status['alarm'] != alarm:
                status['alarm'] = alarm
                changed = True

        if changed and self.callback_area_state_change:
            _LOGGER.debug(f"Updating Area {area_id} State: {status}")
            self.callback_area_state_change(area_id)

    def _notify_system(self):
        if self.callback_system_state_change:
            self.callback_system_state_change(self.system_state)
