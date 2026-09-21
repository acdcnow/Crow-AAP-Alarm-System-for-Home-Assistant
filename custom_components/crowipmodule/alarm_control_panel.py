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
    ARM_SEQUENCE_COMMAND_ONLY,
    ARM_SEQUENCE_COMMAND_THEN_KEYPAD,
    CONF_AREAS,
    CONF_ARM_SEQUENCE,
    CONF_NUM_AREAS,
    DEFAULT_ARM_SEQUENCE,
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
    # The initial config flow stores the arm sequence in entry.data; the options flow
    # rewrites entry.data for the connection-level fields, so read both.
    arm_sequence = entry.options.get(
        CONF_ARM_SEQUENCE,
        entry.data.get(CONF_ARM_SEQUENCE, DEFAULT_ARM_SEQUENCE),
    )

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
                firmware,
                arm_sequence=arm_sequence,
            ))
        except ValueError:
            _LOGGER.error("Invalid area number found in config: %s", area_num_str)

    async_add_entities(devices)

class CrowAlarmPanel(AlarmControlPanelEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(self, controller, host, entry_id, area_number, name, code,
                 code_required, firmware, arm_sequence=DEFAULT_ARM_SEQUENCE) -> None:
        self._controller = controller
        self._host = host
        self._firmware = firmware
        self._arm_sequence = arm_sequence

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

    def _resolve_code(self, code: str | None) -> str:
        """Return the code to send as keypad input, or "" when none is available."""
        if code:
            return str(code)
        return str(self._code or "")

    async def _async_arm(self, *, stay: bool, code: str | None) -> None:
        """Run the configured arm sequence for this area.

        The Crow protocol has no single "arm with code" command. Depending on the
        firmware and how the panel is programmed, either the bare ``ARM``/``STAY``
        command completes the arming, or the panel then waits for the user code
        followed by the Enter key.

        ``send_keypress(code)`` emits ``KEYS <code>E``, where the trailing ``E`` is
        the Enter key, so it is the keypad equivalent of typing the code and
        pressing Enter. That is why the same wire format serves both "complete the
        arming" and "disarm" - the panel decides from its current state.
        """
        label = "ARM STAY" if stay else "ARM AWAY"
        command = self._controller.arm_stay if stay else self._controller.arm_away
        keypad_code = self._resolve_code(code)

        try:
            if self._arm_sequence == ARM_SEQUENCE_COMMAND_ONLY:
                _LOGGER.info("Sending %s command to Area %s", label, self._area_number)
                command()
                return

            # ARM_SEQUENCE_COMMAND_THEN_KEYPAD
            _LOGGER.info(
                "Sending %s command to Area %s, then the user code + Enter",
                label,
                self._area_number,
            )
            command()
            if keypad_code:
                self._controller.send_keypress(keypad_code)
            else:
                _LOGGER.warning(
                    "Arm sequence is '%s' but Area %s has no code configured. Only the "
                    "%s command was sent, which may not complete the arming. Set a code "
                    "for the area, or switch the arm sequence to '%s'.",
                    ARM_SEQUENCE_COMMAND_THEN_KEYPAD,
                    self._area_number,
                    label,
                    ARM_SEQUENCE_COMMAND_ONLY,
                )
        except Exception as err:  # noqa: BLE001 - never raise into the service call
            _LOGGER.error("Error sending %s command: %s", label, err)

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        _LOGGER.info("User requested DISARM for Area %s", self._area_number)
        # Disarming is always keypad style: the code followed by Enter.
        code_to_use = self._resolve_code(code)
        if not code_to_use:
            _LOGGER.error(
                "Cannot disarm Area %s: no code was supplied and none is configured.",
                self._area_number,
            )
            return
        try:
            # disarm() sends "KEYS <code>E" followed by "STATUS".
            self._controller.disarm(code_to_use)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Error sending disarm command: %s", err)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        _LOGGER.info("User requested ARM STAY for Area %s", self._area_number)
        await self._async_arm(stay=True, code=code)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        _LOGGER.info("User requested ARM AWAY for Area %s", self._area_number)
        await self._async_arm(stay=False, code=code)

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
