"""Support for Crow IP Module buttons (Chime toggle, Relay activation)."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    SIGNAL_CONNECTION_UPDATE,
    CONF_FW_VERSION, CONF_FW_DATE,
    DEFAULT_FW_VERSION, DEFAULT_FW_DATE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    fw_version = entry.data.get(CONF_FW_VERSION, DEFAULT_FW_VERSION)
    fw_date = entry.data.get(CONF_FW_DATE, DEFAULT_FW_DATE)

    entities = [
        CrowChimeButton(controller, host, fw_version, fw_date),
        CrowRelayButton(controller, host, 1, "Relay 1", fw_version, fw_date),
        CrowRelayButton(controller, host, 2, "Relay 2", fw_version, fw_date),
    ]
    async_add_entities(entities)


class CrowBaseButton(ButtonEntity):
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

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CONNECTION_UPDATE, self._connection_callback)
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            sw_version=self._fw_string,
            configuration_url=f"http://{self._host}",
        )


class CrowChimeButton(CrowBaseButton):
    _attr_icon = "mdi:bell-ring"

    def __init__(self, controller, host, fw_version, fw_date) -> None:
        super().__init__(controller, host, fw_version, fw_date)
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

    def __init__(self, controller, host, relay_no, name, fw_version, fw_date) -> None:
        super().__init__(controller, host, fw_version, fw_date)
        self._relay_no = relay_no
        self._attr_name = name
        self._attr_unique_id = f"crow_relay_{relay_no}"

    async def async_press(self) -> None:
        _LOGGER.info("Activating relay %s", self._relay_no)
        try:
            self._controller.relay_on(self._relay_no)
        except Exception as e:  # noqa: BLE001
            _LOGGER.error("Error activating relay %s: %s", self._relay_no, e)
