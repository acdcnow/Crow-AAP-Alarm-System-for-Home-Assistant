"""Support for Crow IP Module text sensors."""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    SIGNAL_SYSTEM_UPDATE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Crow IP Module sensor."""
    controller = hass.data[DOMAIN][entry.entry_id]
    host = entry.data[CONF_HOST]
    
    async_add_entities([CrowSystemSensor(controller, host)], True)


class CrowSystemSensor(SensorEntity):
    """Representation of the Crow Alarm System Status Text."""
    
    _attr_has_entity_name = True

    def __init__(self, controller, host) -> None:
        self._controller = controller
        self._host = host
        self._attr_name = "System Status"
        self._attr_unique_id = "crow_system_status_text"
        self._attr_icon = "mdi:shield-home"
        self._info = controller.system_state

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            configuration_url=f"http://{self._host}",
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SYSTEM_UPDATE, self._update_callback)
        )

    @property
    def native_value(self) -> str:
        """Return a text representation of the state."""
        status = self._info.get("status", {})
        
        if status.get("alarm"):
            return "ALARM"
        if status.get("armed"):
            return "Armed Away"
        if status.get("stay_armed"):
            return "Armed Stay"
        if status.get("exit_delay"):
            return "Exit Delay"
        if status.get("stay_exit_delay"):
            return "Stay Exit Delay"
        if not status.get("mains", True):
            return "Power Failure"
        if not status.get("battery", True):
            return "Low Battery"
            
        return "Ready"

    @callback
    def _update_callback(self, system) -> None:
        """Update the sensor state in HA."""
        self._info = self._controller.system_state
        self.async_write_ha_state()
