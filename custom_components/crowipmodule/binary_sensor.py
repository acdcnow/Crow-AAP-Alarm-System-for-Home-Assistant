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
from homeassistant.util import slugify

from .const import (
    CONF_OBJ_BATTERY,
    CONF_OBJ_DIALLER,
    CONF_OBJ_LINE,
    CONF_OBJ_MAINS,
    CONF_OBJ_TAMPER,
    CONF_OBJ_ZONE_BATTERY,
    CONF_ZONES,
    DEVICE_NAME,
    DEVICE_NAME_ZONE_OTHER,
    DOMAIN,
    IDENTIFIER_ZONE_OTHER,
    MODEL_IP_MODULE_ZONE,
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_SYSTEM_UPDATE,
    SIGNAL_ZONE_UPDATE,
    ZONE_DEVICES,
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


def zone_unique_id(zone_number: int) -> str:
    """Return the unique id of a zone's binary sensor.

    Frozen - the registry alignment below looks zone entities up by it.
    """
    return f"crow_zone_{zone_number}"


def zone_device_name(zone_type: str) -> str:
    """Return the device name a zone of this type is grouped into."""
    return ZONE_DEVICES.get(zone_type, (IDENTIFIER_ZONE_OTHER, DEVICE_NAME_ZONE_OTHER))[1]


def zone_device_info(
    runtime_data: CrowRuntimeData, host: str, zone_type: str
) -> DeviceInfo:
    """Return the ``DeviceInfo`` of the device a zone type is grouped into.

    Both the entity and the registry alignment below build their device from
    here, so an entity and its registry entry can never disagree about it.
    """
    identifier, name = ZONE_DEVICES.get(
        zone_type, (IDENTIFIER_ZONE_OTHER, DEVICE_NAME_ZONE_OTHER)
    )
    return build_device_info(
        name=name,
        host=host,
        identifier=identifier,
        model=MODEL_IP_MODULE_ZONE,
        sw_version=runtime_data.firmware,
        via_device_id=runtime_data.device_id,
    )


def _entity_id_was_generated_for_another_type(entity_id: str, zone_type: str) -> bool:
    """Return whether an entity id still names another zone type's device.

    An entity id is ``<domain>.<device name> <entity name>``, so one that was
    generated while the zone still had a different type still starts with that
    type's device name.
    """
    object_id = entity_id.partition(".")[2]
    current = slugify(zone_device_name(zone_type))
    for name in (_all_zone_device_names()):
        if name != current and object_id.startswith(f"{name}_"):
            return True
    return False


def _all_zone_device_names() -> set[str]:
    """Return the slugified device names of every zone group plus the fallback."""
    names = {slugify(name) for _, name in ZONE_DEVICES.values()}
    names.add(slugify(DEVICE_NAME_ZONE_OTHER))
    return names


@callback
def _async_align_zone_entities(
    hass: HomeAssistant,
    runtime_data: CrowRuntimeData,
    host: str,
    configured_zones: dict,
) -> None:
    """Re-link existing zone entities to the device of their configured type.

    Home Assistant links an entity to a device - and derives its entity id from
    that device's name - only when the entity is registered for the very first
    time. A later device change moves the entity but leaves the entity id
    naming the old device, so a zone whose type was changed afterwards keeps an
    entity id of the type it once had (a door zone called
    ``..._windows_terrassentur``, for example).

    Re-derive the device and the entity id from the configured type here, before
    the entities are created, so both always match the type the zone has now.
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
            # rename it when the integration reports another one later. A group
            # device created by an older build under a swapped name would keep
            # handing that name to every entity id generated from it, which is
            # exactly how a window zone ends up called ``..._doors_<name>``.
            _LOGGER.warning(
                "Device %s is named %r but should be %r - correcting the name",
                device.id,
                device.name,
                expected_name,
            )
            device = devices.async_update_device(device.id, name=expected_name)

        entry = registry.async_update_entity(entity_id, device_id=device.id)

        if not _entity_id_was_generated_for_another_type(entry.entity_id, zone_type):
            continue

        expected_id = registry.async_regenerate_entity_id(entry)
        if expected_id == entry.entity_id:
            continue

        try:
            registry.async_update_entity(entry.entity_id, new_entity_id=expected_id)
        except ValueError as err:  # noqa: PERF203 - one bad zone must not stop the rest
            _LOGGER.warning(
                "Could not rename zone entity %s to %s: %s",
                entry.entity_id,
                expected_id,
                err,
            )
            continue

        _LOGGER.info(
            "Zone %s is a %s now: moved %s to %s and renamed it to %s",
            zone_number,
            zone_type,
            entry.entity_id,
            device.name,
            expected_id,
        )


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
        """Return the device that matches this zone's configured type.

        The type is looked up in ``ZONE_DEVICES`` directly - not via the derived
        device class - so a door zone can only ever be registered on the doors
        device and a window zone only on the windows device. Because the device
        name carries the type and ``has_entity_name`` is ``True``, the type also
        becomes part of the entity's own name and entity id.

        The group devices are linked to the main panel with ``via_device_id``.
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
