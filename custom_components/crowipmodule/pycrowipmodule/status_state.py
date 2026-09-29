'''Crow/AAP Alarm IP Module Feedback Class for alarm state'''
import logging

_LOGGER = logging.getLogger(__name__)

class StatusState:
    # Zone State
    @staticmethod
    def get_initial_zone_state(maxZones):
        """Builds the proper zone state collection."""
        _LOGGER.debug(f"Initializing Zone State for {maxZones} zones")
        _zoneState = {}
        for i in range (1, maxZones+1):
            _zoneState[i] = {'status': {'open': False, 'bypass': False, 'alarm': False, 'tamper': False}, 
                                          'last_fault': 0}

        return _zoneState

    # Area State
    @staticmethod
    def get_initial_area_state(maxAreas):
        """Builds the proper alarm state collection."""
        _LOGGER.debug(f"Initializing Area State for {maxAreas} areas")
        _areaState = {}

        for i in range(1, maxAreas+1):
            _areaState[i] = {'status': {'alarm': False, 'armed': False, 'stay_armed': False, 
                                        'disarmed': False,'exit_delay': False, 'stay_exit_delay': False, 
                                        'alarm_zone': '', 'last_disarmed_by_user': '', 
                                        'last_armed_by_user': '' }}

        return _areaState

    # Output State
    @staticmethod
    def get_initial_output_state(maxOutputs):
        _LOGGER.debug(f"Initializing Output State for {maxOutputs} outputs")
        _outputState = {} 
        for i in range (1, maxOutputs+1):
            _outputState[i] = {'status': {'open': False}}
        return _outputState

    # System Status State
    @staticmethod
    def get_initial_system_state():
        _LOGGER.debug("Initializing System State")
        _systemState = {'status':{'mains': True, 'battery': True,'tamper': False, 'line': True, 
                        'dialler': True,'ready': True, 'fuse': True, 'zonebattery': True, 
                'pendantbattery': True, 'codetamper': False}}
        return _systemState
