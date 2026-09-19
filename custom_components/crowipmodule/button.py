"""Support for Crow IP Module buttons (Chime toggle, Relay activation)."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEVICE_NAME, SIGNAL_CONNECTION_UPDATE
from .device import CrowRuntimeData, build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime_data: CrowRuntimeData = entry.runtime_data
    controller = runtime_data.controller
    host = entry.data[CONF_HOST]

    entities = [
        CrowChimeButton(runtime_data, host),
        CrowRelayButton(runtime_data, host, 1, "Relay 1"),
        CrowRelayButton(runtime_data, host, 2, "Relay 2"),
    ]
    async_add_entities(entities)


class CrowBaseButton(ButtonEntity):
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

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CONNECTION_UPDATE, self._connection_callback)
        )

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(
            name=DEVICE_NAME,
            host=self._host,
            sw_version=self._runtime_data.firmware,
        )


class CrowChimeButton(CrowBaseButton):
    _attr_icon = "mdi:bell-ring"

    def __init__(self, runtime_data, host) -> None:
        super().__init__(runtime_data, host)
        self._attr_name = "Toggle Chime"
        self._attr_unique_id = "crow_toggle_chime"

    async def async_press(self) -> None:
        _LOGGER.info("Toggling chime")
        try:
            self._controller.toggle_chime()
        except Exception as e:  # noqa: BLE001
            _LOGGER.error("Error toggling chime: %s", e)


class CrowRelayButton(CrowBaseButton):
    _attr_icon = "mdi:electric-switch"

    def __init__(self, runtime_data, host, relay_no, name) -> None:
        super().__init__(runtime_data, host)
        self._relay_no = relay_no
        self._attr_name = name
        self._attr_unique_id = f"crow_relay_{relay_no}"

    async def async_press(self) -> None:
        _LOGGER.info("Activating relay %s", self._relay_no)
        try:
            self._controller.relay_on(self._relay_no)
        except Exception as e:  # noqa: BLE001
            _LOGGER.error("Error activating relay %s: %s", self._relay_no, e)
