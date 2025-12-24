"""Support for Crow Alarm IP Module Binary Sensors."""
import logging
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.core import callback
from homeassistant.const import CONF_HOST

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
    host = entry.data[CONF_HOST]
    
    entities = []

    # 1. ZONEN
    configured_zones = options.get(CONF_ZONES, {})
    for zone_num_str, zone_info in configured_zones.items():
        zone_num = int(zone_num_str)
        _LOGGER.debug(f"Adding Zone Sensor: {zone_num} ({zone_info['name']})")
        entities.append(CrowZoneSensor(
            controller, host, zone_num, zone_info["name"], zone_info["type"]
        ))

    # 2. SYSTEM STATUS
    system_sensors = [
        (CONF_OBJ_MAINS, "Mains Power", BinarySensorDeviceClass.POWER),
        (CONF_OBJ_BATTERY, "System Battery", BinarySensorDeviceClass.BATTERY),
        (CONF_OBJ_TAMPER, "System Tamper", BinarySensorDeviceClass.TAMPER),
        (CONF_OBJ_LINE, "Phone Line", BinarySensorDeviceClass.CONNECTIVITY),
        (CONF_OBJ_DIALLER, "Dialler", BinarySensorDeviceClass.CONNECTIVITY),
        (CONF_OBJ_ZONE_BATTERY, "Zone Battery", BinarySensorDeviceClass.BATTERY),
    ]

    for key, name, dev_class in system_sensors:
        entities.append(CrowSystemStatusSensor(controller, host, key, name, dev_class))

    async_add_entities(entities)


class CrowBaseEntity(BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, controller, host):
        self._controller = controller
        self._host = host
    
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            configuration_url=f"http://{self._host}",
        )

class CrowZoneSensor(CrowBaseEntity):
    def __init__(self, controller, host, zone_number, zone_name, zone_type):
        super().__init__(controller, host)
        self._zone_number = zone_number
        self._attr_name = zone_name
        self._attr_device_class = zone_type
        self._attr_unique_id = f"crow_zone_{zone_number}"
        self._info = controller.zone_state.get(zone_number, {"status": {"open": False}})

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
            if self._zone_number in self._controller.zone_state:
                self._info = self._controller.zone_state[self._zone_number]
            self.async_write_ha_state()

class CrowSystemStatusSensor(CrowBaseEntity):
    def __init__(self, controller, host, key, name, device_class):
        super().__init__(controller, host)
        self._key = key
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_unique_id = f"crow_sys_{key}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SYSTEM_UPDATE, self._update_callback)
        )

    @property
    def is_on(self):
        status = self._controller.system_state.get("status", {})
        
        # Default True (OK)
        val = status.get(self._key, True) 
        
        # 1. POWER (Mains): True=ON (Connected).
        if self._attr_device_class == BinarySensorDeviceClass.POWER:
            return val
            
        # 2. CONNECTIVITY: True=ON (Connected).
        if self._attr_device_class == BinarySensorDeviceClass.CONNECTIVITY:
            return val

        # 3. BATTERY: HA expects ON for "Low Battery". Crow sends True for "OK".
        if self._attr_device_class == BinarySensorDeviceClass.BATTERY:
            return not val 
            
        # 4. TAMPER: HA expects ON for "Tamper Detected". Crow sends True for "Closed/OK" (usually).
        # Adjust based on observation: if default is False (No Tamper), we return val directly?
        # Standard: Tamper=False (Good). Sensor=Off (Good).
        if self._attr_device_class == BinarySensorDeviceClass.TAMPER:
            return val 

        return val

    @callback
    def _update_callback(self, _):
        self.async_write_ha_state()
