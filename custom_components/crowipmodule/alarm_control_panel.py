"""Support for Crow IP Module Alarm Control Panel."""

from __future__ import annotations

import logging

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_AREAS,
    CONF_NUM_AREAS,
    DEFAULT_NUM_AREAS,
    DEVICE_NAME,
    SIGNAL_AREA_UPDATE,
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_KEYPAD_UPDATE,
)
from .device import build_device_info

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    _LOGGER.debug("Setting up Alarm Control Panel entities...")
    controller = entry.runtime_data.controller
    options = entry.options
    host = entry.data[CONF_HOST]
    firmware = entry.runtime_data.firmware

    configured_areas = options.get(CONF_AREAS, {})

    if not configured_areas:
        # Fall back to creating bare area entries based on the configured count
        num_areas = entry.data.get(CONF_NUM_AREAS, DEFAULT_NUM_AREAS)
        configured_areas = {
            str(i): {"name": f"Area {i}", "code": "", "code_arm_required": True}
            for i in range(1, num_areas + 1)
        }

    devices = []
    for area_num_str, area_data in configured_areas.items():
        try:
            area_num = int(area_num_str)
            devices.append(CrowAlarmPanel(
                controller, host,
                entry.entry_id,
                area_num,
                area_data.get("name", f"Area {area_num}"),
                area_data.get("code", ""),
                area_data.get("code_arm_required", True),
                firmware
            ))
        except ValueError:
            _LOGGER.error("Invalid area number found in config: %s", area_num_str)

    async_add_entities(devices)

class CrowAlarmPanel(AlarmControlPanelEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(self, controller, host, entry_id, area_number, name, code, code_required, firmware) -> None:
        self._controller = controller
        self._host = host
        self._firmware = firmware

        self._area_number_int = area_number
        self._area_number = "A" if area_number == 1 else "B"

        self._attr_name = name
        # Include entry_id so unique_id is scoped per config entry and entity_id
        # is generated from the correct area name on first registration.
        self._attr_unique_id = f"{entry_id}_crow_area_{area_number}"
        self._attr_icon = "mdi:shield-home"
        
        self._code = code
        self._code_arm_required_config = code_required
        
        self._info = controller.area_state.get(area_number, {"status": {}})

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(
            name=DEVICE_NAME,
            host=self._host,
            sw_version=self._firmware,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_AREA_UPDATE, self._update_callback)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_KEYPAD_UPDATE, self._update_callback)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CONNECTION_UPDATE, self._connection_callback)
        )

    @callback
    def _connection_callback(self, _connected) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self._controller.is_connected

    @callback
    def _update_callback(self, area) -> None:
        if area is None or area == self._area_number:
            if self._area_number_int in self._controller.area_state:
                self._info = self._controller.area_state[self._area_number_int]
            self.async_write_ha_state()

    @property
    def code_format(self) -> CodeFormat | None:
        # Always return NUMBER so HA knows the input type and renders arm/disarm
        # buttons correctly. Visibility of the code field is controlled by
        # code_arm_required below.
        return CodeFormat.NUMBER

    @property
    def code_arm_required(self) -> bool:
        # If a code is pre-stored in config the user never needs to type one;
        # it is sent internally. Return False so HA makes the field optional.
        if self._code:
            return False
        return self._code_arm_required_config

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        return (
            AlarmControlPanelEntityFeature.ARM_HOME
            | AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.TRIGGER
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        _LOGGER.info("User requested DISARM for Area %s", self._area_number)
        code_to_use = str(code) if code else str(self._code)
        try:
            self._controller.disarm(code_to_use)
        except Exception as e:
             _LOGGER.error("Error sending disarm command: %s", e)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        _LOGGER.info("User requested ARM STAY for Area %s", self._area_number)
        try:
            # ARM/STAY commands are standalone on the Crow protocol - no code follow-up.
            # Calling send_keypress here would send a KEYS command (identical to disarm)
            # and immediately cancel the arm.
            self._controller.arm_stay()
        except Exception as e:
             _LOGGER.error("Error sending arm home command: %s", e)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        _LOGGER.info("User requested ARM AWAY for Area %s", self._area_number)
        try:
            self._controller.arm_away()
        except Exception as e:
             _LOGGER.error("Error sending arm away command: %s", e)

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        _LOGGER.warning("User requested PANIC TRIGGER for Area %s", self._area_number)
        try:
            self._controller.panic_alarm("")
        except Exception as e:
            _LOGGER.error("Error triggering panic: %s", e)

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the state of the device."""
        status = self._info.get("status", {})
        
        if status.get("alarm"): 
            return AlarmControlPanelState.TRIGGERED
        if status.get("armed"): 
            return AlarmControlPanelState.ARMED_AWAY
        if status.get("stay_armed"): 
            return AlarmControlPanelState.ARMED_HOME
        if status.get("exit_delay") or status.get("stay_exit_delay"): 
            return AlarmControlPanelState.ARMING
        if status.get("disarmed"): 
            return AlarmControlPanelState.DISARMED
        
        return None
    
    @property
    def extra_state_attributes(self):
        return self._info.get("status", {})
