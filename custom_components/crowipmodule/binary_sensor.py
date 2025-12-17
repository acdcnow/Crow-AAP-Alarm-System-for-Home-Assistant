"""Support for Crow Alarm IP Module Binary Sensors."""
import logging
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.core import callback

from .const import (
    DOMAIN, SIGNAL_ZONE_UPDATE, SIGNAL_SYSTEM_UPDATE,
    CONF_ZONES, CONF_OBJ_MAINS, CONF_OBJ_BATTERY, 
    CONF_OBJ_TAMPER, CONF_OBJ_LINE, CONF_OBJ_DIALLER, CONF_OBJ_ZONE_BATTERY
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the Crow binary sensors."""
    controller = hass.data[DOMAIN][entry.entry_id]
    options = entry.options
    
    entities = []

    configured_zones = options.get(CONF_ZONES, {})
    for zone_num_str, zone_info in configured_zones.items():
        zone_num = int(zone_num_str)
        entities.append(CrowZoneSensor(
            controller, zone_num, zone_info["name"], zone_info["type"]
        ))

    system_sensors = [
        (CONF_OBJ_MAINS, "Mains Power", BinarySensorDeviceClass.POWER),
        (CONF_OBJ_BATTERY, "System Battery", BinarySensorDeviceClass.BATTERY),
        (CONF_OBJ_TAMPER, "System Tamper", BinarySensorDeviceClass.TAMPER),
        (CONF_OBJ_LINE, "Phone Line", BinarySensorDeviceClass.CONNECTIVITY),
        (CONF_OBJ_DIALLER, "Dialler", BinarySensorDeviceClass.CONNECTIVITY),
        (CONF_OBJ_ZONE_BATTERY, "Zone Battery", BinarySensorDeviceClass.BATTERY),
    ]

    for key, name, dev_class in system_sensors:
        entities.append(CrowSystemStatusSensor(controller, key, name, dev_class))

    async_add_entities(entities)


class CrowBaseEntity(BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, controller):
        self._controller = controller
    
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            configuration_url=f"http://{self._controller.ip}",
        )

class CrowZoneSensor(CrowBaseEntity):
    def __init__(self, controller, zone_number, zone_name, zone_type):
        super().__init__(controller)
        self._zone_number = zone_number
        self._attr_name = zone_name
        self._attr_device_class = zone_type
        self._attr_unique_id = f"crow_zone_{zone_number}"
        self._info = controller.zone_state[zone_number]

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_ZONE_UPDATE, self._update_callback)
        )

    @property
    def is_on(self):
        return self._info["status"]["open"]

    @property
    def extra_state_attributes(self):
        return self._info["status"]

    @callback
    def _update_callback(self, zone):
        if zone is None or int(zone) == self._zone_number:
            self.async_write_ha_state()

class CrowSystemStatusSensor(CrowBaseEntity):
    def __init__(self, controller, key, name, device_class):
        super().__init__(controller)
        self._key = key
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_unique_id = f"crow_sys_{key}"
        self._attr_entity_category = "diagnostic" 

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SYSTEM_UPDATE, self._update_callback)
        )

    @property
    def is_on(self):
        val = self._controller.system_state["status"].get(self._key)
        if self._attr_device_class == BinarySensorDeviceClass.POWER:
            return val
        if self._attr_device_class == BinarySensorDeviceClass.BATTERY:
            return not val # Invert logic often needed for batteries (On = Low)
        return val

    @callback
    def _update_callback(self, _):
        self.async_write_ha_state()
