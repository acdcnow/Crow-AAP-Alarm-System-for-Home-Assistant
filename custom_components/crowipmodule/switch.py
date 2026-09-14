"""Support for Crow IP Module switches (Outputs)."""
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    SIGNAL_OUTPUT_UPDATE,
    SIGNAL_CONNECTION_UPDATE,
    CONF_OUTPUTS,
    CONF_FW_VERSION, CONF_FW_DATE,
    DEFAULT_FW_VERSION, DEFAULT_FW_DATE
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    options = entry.options
    host = entry.data[CONF_HOST]
    
    # Firmware Infos laden
    fw_version = entry.data.get(CONF_FW_VERSION, DEFAULT_FW_VERSION)
    fw_date = entry.data.get(CONF_FW_DATE, DEFAULT_FW_DATE)
    
    entities = []
    configured_outputs = options.get(CONF_OUTPUTS, None)

    # Only fall back to defaults when the integration has never been configured
    # (options key absent entirely). An empty dict means the user set outputs to 0.
    if configured_outputs is None:
        from .const import CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS
        num = entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS)
        configured_outputs = {str(i): {"name": f"Output {i}"} for i in range(1, num + 1)}

    for output_num_str, output_data in configured_outputs.items():
        try:
            output_num = int(output_num_str)
            name = output_data.get("name", f"Output {output_num}")
            entities.append(CrowOutput(controller, host, output_num, name, fw_version, fw_date))
        except ValueError:
            _LOGGER.error("Invalid output number: %s", output_num_str)

    async_add_entities(entities)


class CrowBaseSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller, host, fw_version, fw_date):
        self._controller = controller
        self._host = host
        self._fw_string = f"{fw_version} ({fw_date})"

    @property
    def available(self) -> bool:
        return self._controller.is_connected

    @callback
    def _connection_callback(self, _connected) -> None:
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            sw_version=self._fw_string, # Konsistente Version
            configuration_url=f"http://{self._host}",
        )


class CrowOutput(CrowBaseSwitch):
    def __init__(self, controller, host, output_number, output_name, fw_version, fw_date) -> None:
        super().__init__(controller, host, fw_version, fw_date)
        self._output_number = output_number
        self._attr_name = output_name
        self._attr_unique_id = f"crow_output_{output_number}"
        self._is_on = False
        
        if self._output_number in self._controller.output_state:
             self._is_on = self._controller.output_state[self._output_number].get("status", {}).get("open", False)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_OUTPUT_UPDATE, self._update_callback)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CONNECTION_UPDATE, self._connection_callback)
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._is_on:
            return
        _LOGGER.info("Turn ON Output %s", self._output_number)
        try:
            self._controller.command_output(str(self._output_number))
            self._is_on = True
            self.async_write_ha_state()
        except Exception as e:
             _LOGGER.error("Error switching output ON: %s", e)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if not self._is_on:
            return
        _LOGGER.info("Turn OFF Output %s", self._output_number)
        try:
            self._controller.command_output(str(self._output_number))
            self._is_on = False
            self.async_write_ha_state()
        except Exception as e:
             _LOGGER.error("Error switching output OFF: %s", e)

    @callback
    def _update_callback(self, output) -> None:
        if output is None or int(output) == self._output_number:
            if self._output_number in self._controller.output_state:
                new_state = self._controller.output_state[self._output_number]["status"]["open"]
                if self._is_on != new_state:
                    self._is_on = new_state
                    self.async_write_ha_state()
