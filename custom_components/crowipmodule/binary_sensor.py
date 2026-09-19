"""Support for Crow Alarm IP Module Binary Sensors."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_OBJ_BATTERY,
    CONF_OBJ_DIALLER,
    CONF_OBJ_LINE,
    CONF_OBJ_MAINS,
    CONF_OBJ_TAMPER,
    CONF_OBJ_ZONE_BATTERY,
    CONF_ZONES,
    DEVICE_NAME,
    DEVICE_NAME_DOORS,
    DEVICE_NAME_SENSORS,
    DEVICE_NAME_WINDOWS,
    IDENTIFIER_DOORS,
    IDENTIFIER_SENSORS,
    IDENTIFIER_WINDOWS,
    MODEL_IP_MODULE_ZONE,
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_SYSTEM_UPDATE,
    SIGNAL_ZONE_UPDATE,
)
from .device import CrowRuntimeData, build_device_info

_LOGGER = logging.getLogger(__name__)

# Map configured zone type strings to valid BinarySensorDeviceClass values.
_ZONE_DEVICE_CLASSES = {
    "window": BinarySensorDeviceClass.WINDOW,
    "door": BinarySensorDeviceClass.DOOR,
    "motion": BinarySensorDeviceClass.MOTION,
    "smoke": BinarySensorDeviceClass.SMOKE,
    "gas": BinarySensorDeviceClass.GAS,
    "co": BinarySensorDeviceClass.CO,
    "tamper": BinarySensorDeviceClass.TAMPER,
    "safety": BinarySensorDeviceClass.SAFETY,
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Crow zone and system status binary sensors."""
    runtime_data: CrowRuntimeData = entry.runtime_data
    controller = runtime_data.controller
    options = entry.options
    host = entry.data[CONF_HOST]

    entities = []

    # 1. Zone Sensors
    configured_zones = options.get(CONF_ZONES, {})
    if not configured_zones:
        for i in range(1, 17):
            configured_zones[str(i)] = {"name": f"Zone {i}", "type": "window"}

    for zone_num_str, zone_info in configured_zones.items():
        try:
            zone_num = int(zone_num_str)
            entities.append(CrowZoneSensor(
                runtime_data, host, zone_num, zone_info["name"], zone_info["type"]
            ))
        except ValueError:
             _LOGGER.warning("Skipping invalid zone config key: %s", zone_num_str)

    # 2. System Status Sensors
    system_sensors = [
        (CONF_OBJ_MAINS, "Mains Power", BinarySensorDeviceClass.POWER),
        (CONF_OBJ_BATTERY, "System Battery", BinarySensorDeviceClass.BATTERY),
        (CONF_OBJ_TAMPER, "System Tamper", BinarySensorDeviceClass.TAMPER),
        (CONF_OBJ_LINE, "Phone Line", BinarySensorDeviceClass.CONNECTIVITY),
        (CONF_OBJ_DIALLER, "Dialler", BinarySensorDeviceClass.CONNECTIVITY),
        (CONF_OBJ_ZONE_BATTERY, "Zone Battery", BinarySensorDeviceClass.BATTERY),
    ]

    for key, name, dev_class in system_sensors:
        entities.append(CrowSystemStatusSensor(runtime_data, host, key, name, dev_class))

    async_add_entities(entities)


class CrowBaseEntity(BinarySensorEntity):
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
    def _connection_callback(self, _connected):
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Device info for the main alarm panel device."""
        return build_device_info(
            name=DEVICE_NAME,
            host=self._host,
            sw_version=self._runtime_data.firmware,
        )


class CrowZoneSensor(CrowBaseEntity):
    def __init__(self, runtime_data, host, zone_number, zone_name, zone_type):
        super().__init__(runtime_data, host)
        self._zone_number = zone_number
        self._attr_name = zone_name
        self._attr_device_class = _ZONE_DEVICE_CLASSES.get(zone_type)
        if self._attr_device_class is None and zone_type:
            _LOGGER.warning("Unknown zone type '%s' for zone %s; no device class set", zone_type, zone_number)
        self._attr_unique_id = f"crow_zone_{zone_number}"
        self._info = runtime_data.controller.zone_state.get(
            zone_number, {"status": {"open": False}}
        )

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_ZONE_UPDATE, self._update_callback)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CONNECTION_UPDATE, self._connection_callback)
        )

    @property
    def is_on(self):
        if not self._info or "status" not in self._info:
            return False
        return self._info["status"].get("open", False)

    @property
    def extra_state_attributes(self):
        return self._info.get("status", {})

    @callback
    def _update_callback(self, zone):
        if zone is None or int(zone) == self._zone_number:
            if self._zone_number in self._controller.zone_state:
                self._info = self._controller.zone_state[self._zone_number]
            self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group entities by zone type.

        The group devices are linked to the main panel with ``via_device_id``.
        The identifier tuple based ``via_device`` used before is deprecated in
        Home Assistant and is removed in 2027.8.
        """
        # Determine the group based on the zone type (device class).
        if self._attr_device_class == BinarySensorDeviceClass.WINDOW:
            device_name = DEVICE_NAME_WINDOWS
            device_identifier = IDENTIFIER_WINDOWS
        elif self._attr_device_class == BinarySensorDeviceClass.DOOR:
            device_name = DEVICE_NAME_DOORS
            device_identifier = IDENTIFIER_DOORS
        else:
            # Group motion, smoke, and other sensors together.
            device_name = DEVICE_NAME_SENSORS
            device_identifier = IDENTIFIER_SENSORS

        return build_device_info(
            name=device_name,
            host=self._host,
            identifier=device_identifier,
            model=MODEL_IP_MODULE_ZONE,
            sw_version=self._runtime_data.firmware,
            via_device_id=self._runtime_data.device_id,
        )


class CrowSystemStatusSensor(CrowBaseEntity):
    """Sensor for System Statuses (Mains, Battery, etc)."""
    
    def __init__(self, runtime_data, host, key, name, device_class):
        super().__init__(runtime_data, host)
        self._key = key
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_unique_id = f"crow_sys_{key}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SYSTEM_UPDATE, self._update_callback)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CONNECTION_UPDATE, self._connection_callback)
        )

    @property
    def is_on(self):
        status = self._controller.system_state.get("status", {})
        val = status.get(self._key, True) 
        
        if self._attr_device_class in [BinarySensorDeviceClass.POWER, BinarySensorDeviceClass.CONNECTIVITY]:
            return val
            
        if self._attr_device_class == BinarySensorDeviceClass.BATTERY:
            return not val 

        if self._attr_device_class == BinarySensorDeviceClass.TAMPER:
            return val

        return val

    @callback
    def _update_callback(self, _):
        self.async_write_ha_state()
