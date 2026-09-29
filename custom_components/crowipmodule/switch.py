"""Support for Crow IP Module switches (Outputs)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_NUM_OUTPUTS,
    CONF_OUTPUTS,
    DEFAULT_NUM_OUTPUTS,
    DEVICE_NAME,
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_OUTPUT_UPDATE,
)
from .device import CrowRuntimeData, build_device_info

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime_data: CrowRuntimeData = entry.runtime_data
    controller = runtime_data.controller
    options = entry.options
    host = entry.data[CONF_HOST]

    entities = []
    configured_outputs = options.get(CONF_OUTPUTS, None)

    # Only fall back to defaults when the integration has never been configured
    # (options key absent entirely). An empty dict means the user set outputs to 0.
    if configured_outputs is None:
        num = entry.data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS)
        configured_outputs = {str(i): {"name": f"Output {i}"} for i in range(1, num + 1)}

    for output_num_str, output_data in configured_outputs.items():
        try:
            output_num = int(output_num_str)
            name = output_data.get("name", f"Output {output_num}")
            entities.append(CrowOutput(runtime_data, host, output_num, name))
        except ValueError:
            _LOGGER.error("Invalid output number: %s", output_num_str)

    async_add_entities(entities)


class CrowBaseSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime_data: CrowRuntimeData, host: str) -> None:
        self._runtime_data = runtime_data
        self._controller = runtime_data.controller
        self._host = host

    @property
    def available(self) -> bool:
        return self._controller.is_connected

    @callback
    def _connection_callback(self, _connected) -> None:
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(
            name=DEVICE_NAME,
            host=self._host,
            sw_version=self._runtime_data.firmware,
        )


class CrowOutput(CrowBaseSwitch):
    def __init__(self, runtime_data, host, output_number, output_name) -> None:
        super().__init__(runtime_data, host)
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
