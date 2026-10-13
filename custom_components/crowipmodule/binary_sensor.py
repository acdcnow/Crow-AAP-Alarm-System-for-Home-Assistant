"""Support for Crow Alarm IP Module Binary Sensors."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
    DOMAIN,
    LEGACY_ZONE_IDENTIFIERS,
    MODEL_IP_MODULE_ZONE,
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_SYSTEM_UPDATE,
    SIGNAL_ZONE_UPDATE,
    zone_device,
)
from .device import CrowRuntimeData, build_device_info
from .entity import CrowConnectionEntity

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


def zone_unique_id(zone_number: int) -> str:
    """Return the unique id of a zone's binary sensor.

    Frozen - the registry alignment below looks zone entities up by it.
    """
    return f"crow_zone_{zone_number}"


def zone_device_name(zone_type: str) -> str:
    """Return the device name a zone of this type is grouped into."""
    return zone_device(zone_type)[1]


def zone_device_info(
    runtime_data: CrowRuntimeData, host: str, zone_type: str
) -> DeviceInfo:
    """Return the ``DeviceInfo`` of the device the zone entities live on.

    Both the entity and the registry alignment below build their device from
    here, so an entity and its registry entry can never disagree about it.
    """
    identifier, name = zone_device(zone_type)
    return build_device_info(
        name=name,
        host=host,
        identifier=identifier,
        model=MODEL_IP_MODULE_ZONE,
        sw_version=runtime_data.firmware,
        via_device_id=runtime_data.device_id,
    )


def _remove_retired_zone_devices(hass: HomeAssistant) -> None:
    """Remove the per-type zone devices of releases up to 2.1.4 once empty.

    Every zone entity lives on one device now, so the former *Windows* / *Doors* /
    *Motion* / ... devices are dead weight in the device list. A device is only
    removed when nothing is registered on it any more, so this can never take an
    entity away from a user.
    """
    devices = dr.async_get(hass)
    entities = er.async_get(hass)

    for identifier in LEGACY_ZONE_IDENTIFIERS:
        device = devices.async_get_device(identifiers={(DOMAIN, identifier)})
        if device is None:
            continue
        if er.async_entries_for_device(
            entities, device.id, include_disabled_entities=True
        ):
            continue
        _LOGGER.info("Removing the retired zone device %r", device.name)
        devices.async_remove_device(device.id)


@callback
def _async_align_zone_entities(
    hass: HomeAssistant,
    runtime_data: CrowRuntimeData,
    host: str,
    configured_zones: dict,
) -> None:
    """Move existing zone entities onto the single zone device.

    Home Assistant links an entity to a device only when it is registered for the
    very first time, so an entity that was created while the zones still had their
    own devices would keep that device forever - unless the integration re-links
    it, which is what happens here, before the entities are created.

    Entity ids are left exactly as they are: they are stable handles for
    dashboards and automations, and only the device they hang off changes.
    """
    registry = er.async_get(hass)
    devices = dr.async_get(hass)

    for zone_key, zone_info in configured_zones.items():
        try:
            zone_number = int(zone_key)
        except (TypeError, ValueError):
            continue

        unique_id = zone_unique_id(zone_number)
        entity_id = registry.async_get_entity_id(
            Platform.BINARY_SENSOR, DOMAIN, unique_id
        )
        if entity_id is None:
            _LOGGER.debug(
                "Zone %s %r is not registered yet", zone_number, zone_info.get("name")
            )
            continue

        entry = registry.async_get(entity_id)
        if entry is None or entry.config_entry_id != runtime_data.entry_id:
            continue

        zone_type = zone_info.get("type")
        device = devices.async_get_or_create(
            config_entry_id=entry.config_entry_id,
            **zone_device_info(runtime_data, host, zone_type),
        )

        expected_name = zone_device_name(zone_type)
        if device.name != expected_name:
            # A device keeps the name it was created with - Home Assistant does not
            # rename it when the integration reports another one later.
            _LOGGER.warning(
                "Zone device %s is named %r but should be %r - correcting the name",
                device.id,
                device.name,
                expected_name,
            )
            device = devices.async_update_device(device.id, name=expected_name)

        previous_device_id = entry.device_id
        if previous_device_id != device.id:
            registry.async_update_entity(entity_id, device_id=device.id)
            _LOGGER.info(
                "Zone %s %r (%s) moved from device %s to %r (entity id unchanged: %s)",
                zone_number,
                zone_info.get("name"),
                zone_type,
                previous_device_id,
                device.name,
                entity_id,
            )

        _LOGGER.debug(
            "Zone %s %r (%s) -> device %r, entity %s",
            zone_number,
            zone_info.get("name"),
            zone_type,
            device.name,
            entity_id,
        )

    _remove_retired_zone_devices(hass)


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

    # One line with the zone -> type map the entities below are built from, so a
    # zone that is grouped unexpectedly can be traced back to its stored type.
    _LOGGER.info(
        "Zone types: %s",
        ", ".join(
            f"{key} {info.get('name')!r}={info.get('type')}"
            for key, info in sorted(
                configured_zones.items(),
                key=lambda item: int(item[0]) if str(item[0]).isdigit() else 0,
            )
        ),
    )

    # Bring zone entities that were registered under an earlier type onto the
    # device of the type the zone has now (before they are added again).
    _async_align_zone_entities(hass, runtime_data, host, configured_zones)

    for zone_num_str, zone_info in configured_zones.items():
        try:
            zone_num = int(zone_num_str)
            entities.append(CrowZoneSensor(
                runtime_data, host, zone_num, zone_info["name"], zone_info.get("type")
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


class CrowBaseEntity(CrowConnectionEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime_data: CrowRuntimeData, host: str) -> None:
        self._runtime_data = runtime_data
        self._controller = runtime_data.controller
        self._host = host

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
        self._zone_type = zone_type
        self._attr_name = zone_name
        self._attr_device_class = _ZONE_DEVICE_CLASSES.get(zone_type)
        if self._attr_device_class is None and zone_type:
            _LOGGER.warning("Unknown zone type '%s' for zone %s; no device class set", zone_type, zone_number)
        self._attr_unique_id = zone_unique_id(zone_number)
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
        """Return the device all zone entities live on.

        The zone type decides the binary-sensor device class (the icon), not the
        device: every zone is registered on the one *Crow Alarm Sensors* device,
        which is linked to the main panel with ``via_device_id``. With Home
        Assistant only linking an entity to a device at first registration, a
        single device is what makes the assignment independent of when a zone was
        configured or re-typed.

        The identifier tuple based ``via_device`` used before is deprecated in
        Home Assistant and is removed in 2027.8.
        """
        return zone_device_info(self._runtime_data, self._host, self._zone_type)


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
