"""Verify the Crow IP Module integration against the HA 2026.9.3 entity contract.

Home Assistant 2026.9 needs Python >= 3.14.2, so it cannot be imported here.
Instead this harness injects faithful stubs for the Home Assistant modules the
integration imports, using the *real* 2026.9.3 definitions for the parts that
matter (``DeviceInfo`` is a total=False TypedDict whose only required key is
``via_device_id``; ``BinarySensorDeviceClass`` is a StrEnum; ``EntityCategory``
lives in ``homeassistant.const``).

Run:  python tests/verify_ha_2026_contract.py
"""

from __future__ import annotations

import asyncio
import enum
import pathlib
import re
import sys
import types
import unicodedata
from typing import NotRequired, Required, TypedDict

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FAILURES: list[str] = []


def check(label: str, condition: bool, extra: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {label}{(' -> ' + extra) if extra and not condition else ''}")
    if not condition:
        FAILURES.append(label)


# --------------------------------------------------------------------------- #
# Minimal but faithful Home Assistant stubs
# --------------------------------------------------------------------------- #
def mod(name: str) -> types.ModuleType:
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


ha = mod("homeassistant")
ha_const = mod("homeassistant.const")
ha_core = mod("homeassistant.core")
ha_ce = mod("homeassistant.config_entries")
ha_helpers = mod("homeassistant.helpers")
ha_comp = mod("homeassistant.components")
for name in ("homeassistant.helpers", "homeassistant.components"):
    sys.modules[name].__path__ = []
ha.helpers = ha_helpers
ha.components = ha_comp
ha.const = ha_const
ha.core = ha_core

# --- homeassistant.const ---------------------------------------------------- #
ha_const.CONF_HOST = "host"
ha_const.CONF_PORT = "port"
ha_const.CONF_TIMEOUT = "timeout"
ha_const.EVENT_HOMEASSISTANT_STOP = "homeassistant_stop"


class Platform(enum.StrEnum):
    ALARM_CONTROL_PANEL = "alarm_control_panel"
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    SENSOR = "sensor"
    SWITCH = "switch"


class EntityCategory(enum.StrEnum):
    DIAGNOSTIC = "diagnostic"
    CONFIG = "config"


ha_const.Platform = Platform
ha_const.EntityCategory = EntityCategory

# --- homeassistant.core ----------------------------------------------------- #
class Event:
    pass


def callback(func):
    return func


class HomeAssistant:
    pass


ha_core.Event = Event
ha_core.callback = callback
ha_core.HomeAssistant = HomeAssistant

# --- homeassistant.config_entries ------------------------------------------- #
class ConfigEntry:
    pass


ha_ce.ConfigEntry = ConfigEntry

# --- homeassistant.helpers.device_registry ---------------------------------- #
dr = mod("homeassistant.helpers.device_registry")


class DeviceInfo(TypedDict, total=False):
    """Verbatim HA 2026.9.3 DeviceInfo contract."""

    configuration_url: str | None
    connections: set[tuple[str, str]]
    entry_type: str | None
    identifiers: set[tuple[str, str]]
    manufacturer: str | None
    model: str | None
    model_id: str | None
    name: str | None
    serial_number: str | None
    suggested_area: str | None
    sw_version: str | None
    hw_version: str | None
    translation_key: str | None
    translation_placeholders: dict[str, str] | None
    via_device_id: str


class FakeDeviceEntry:
    def __init__(self, device_id: str, fields: dict) -> None:
        self.id = device_id
        self.fields = fields
        self.name = fields.get("name")
        self.name_by_user = None
        self.identifiers = fields.get("identifiers") or set()


class FakeDeviceRegistry:
    """Mimics DeviceRegistry.async_get_or_create for the calls we make."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], FakeDeviceEntry] = {}
        self.created: list[dict] = []
        self.removed: list[str] = []
        self._counter = 0

    def async_get_or_create(self, *, config_entry_id: str, **kwargs):
        # HA raises ValueError for a bad configuration_url - mirror that.
        url = kwargs.get("configuration_url")
        if url is not None:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https", "homeassistant") or not parsed.hostname:
                raise ValueError(f"invalid configuration_url '{url}'")
        if "via_device" in kwargs:
            raise ValueError("via_device must not be used")
        identifiers = kwargs["identifiers"]
        key = next(iter(identifiers))
        if key not in self.entries:
            self._counter += 1
            self.entries[key] = FakeDeviceEntry(f"device{self._counter}", kwargs)
            self.created.append({"id": self.entries[key].id, "config_entry_id": config_entry_id, **kwargs})
        return self.entries[key]

    def async_update_device(self, device_id, *, name=..., **kwargs):
        entry = next(e for e in self.entries.values() if e.id == device_id)
        if name is not ...:
            entry.fields["name"] = name
            entry.name = name
        return entry

    def async_get(self, device_id, **kwargs):
        return next((e for e in self.entries.values() if e.id == device_id), None)

    def async_get_device(self, identifiers=None, connections=None):
        if identifiers:
            key = next(iter(identifiers))
            return self.entries.get(key)
        return None

    def async_remove_device(self, device_id):
        for key, entry in list(self.entries.items()):
            if entry.id == device_id:
                del self.entries[key]
                self.removed.append(device_id)


REGISTRY = FakeDeviceRegistry()
dr.DeviceInfo = DeviceInfo
dr.async_get = lambda hass: REGISTRY
ha_helpers.device_registry = dr


def device_id_for_identifier(identifier: str) -> str:
    """Return the registry id of a device created for an identifier."""
    return REGISTRY.entries[(crow_const_domain, identifier)].id


crow_const_domain = "crowipmodule"

# --- homeassistant.util ----------------------------------------------------- #
ha_util = mod("homeassistant.util")


def slugify(text: str) -> str:
    """Same result as homeassistant.util.slugify for the names used here."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


ha_util.slugify = slugify
ha.util = ha_util

# --- homeassistant.helpers.entity_registry ---------------------------------- #
er = mod("homeassistant.helpers.entity_registry")
ha_helpers.entity_registry = er


class FakeRegistryEntry:
    """The subset of RegistryEntry the integration reads/writes."""

    def __init__(self, entity_id, unique_id, *, device_id, config_entry_id="entry-1",
                 object_id_base=None, name=None, has_entity_name=True):
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.domain = entity_id.partition(".")[0]
        self.platform = "crowipmodule"
        self.device_id = device_id
        self.config_entry_id = config_entry_id
        self.area_id = None
        self.object_id_base = object_id_base
        self.name = name
        self.suggested_object_id = None
        self.has_entity_name = has_entity_name
        self.disabled_by = None


class FakeEntityRegistry:
    """Mimics the parts of EntityRegistry the zone alignment uses."""

    def __init__(self) -> None:
        self.entries: dict[str, FakeRegistryEntry] = {}

    def add(self, entry: FakeRegistryEntry) -> None:
        self.entries[entry.entity_id] = entry

    def async_get(self, entity_id):
        return self.entries.get(entity_id)

    def async_get_entity_id(self, domain, platform, unique_id):
        for entry in self.entries.values():
            if entry.unique_id == unique_id and entry.domain == domain:
                return entry.entity_id
        return None

    def async_update_entity(self, entity_id, *, device_id=..., new_entity_id=...):
        entry = self.entries[entity_id]
        if device_id is not ...:
            entry.device_id = device_id
        if new_entity_id is not ...:
            self.entries.pop(entity_id)
            entry.entity_id = new_entity_id
            self.entries[new_entity_id] = entry
        return entry

    def async_regenerate_entity_id(self, entry, *, reserved_entity_ids=None):
        """Mirror HA: <domain>.<device name> <object_id_base>, slugified."""
        device = next(
            (d for d in REGISTRY.entries.values() if d.id == entry.device_id), None
        )
        device_name = (device.fields.get("name") if device else "") or ""
        base = f"{device_name} {entry.object_id_base}".strip()
        candidate = f"{entry.domain}.{slugify(base)}"
        tries = 1
        while candidate in self.entries and candidate != entry.entity_id:
            tries += 1
            candidate = f"{entry.domain}.{slugify(base)}_{tries}"
        return candidate


ENTITY_REGISTRY = FakeEntityRegistry()
er.async_get = lambda hass: ENTITY_REGISTRY
er.async_entries_for_config_entry = lambda registry, config_entry_id: [
    entry
    for entry in registry.entries.values()
    if entry.config_entry_id == config_entry_id
]
er.async_entries_for_device = lambda registry, device_id, include_disabled_entities=False: [
    entry for entry in registry.entries.values() if entry.device_id == device_id
]

# --- homeassistant.helpers.dispatcher --------------------------------------- #
disp = mod("homeassistant.helpers.dispatcher")
disp.async_dispatcher_connect = lambda hass, signal, target: (lambda: None)
disp.async_dispatcher_send = lambda hass, signal, data=None: None

# --- homeassistant.helpers.entity_platform ---------------------------------- #
ep = mod("homeassistant.helpers.entity_platform")
ep.AddConfigEntryEntitiesCallback = object
ep.AddEntitiesCallback = object

# --- homeassistant.helpers.entity ------------------------------------------- #
ent = mod("homeassistant.helpers.entity")


class Entity:
    """Mimics the parts of homeassistant.helpers.entity.Entity we rely on."""

    _attr_has_entity_name = False
    _attr_should_poll = True
    _attr_unique_id: str | None = None
    _attr_name: str | None = None
    _attr_icon: str | None = None
    _attr_device_class = None
    _attr_entity_category = None
    _attr_available = True
    _attr_device_info = None

    hass = None
    entity_id = "test.entity"

    def async_write_ha_state(self) -> None:
        self.state_writes = getattr(self, "state_writes", 0) + 1

    def async_on_remove(self, func) -> None:
        self._on_remove = getattr(self, "_on_remove", [])
        self._on_remove.append(func)

    # HA exposes these as cached properties over the _attr_ backing values.
    @property
    def should_poll(self) -> bool:
        return self._attr_should_poll

    @property
    def unique_id(self) -> str | None:
        return self._attr_unique_id

    @property
    def name(self) -> str | None:
        return self._attr_name

    @property
    def icon(self) -> str | None:
        return self._attr_icon

    @property
    def device_class(self):
        return self._attr_device_class

    @property
    def entity_category(self):
        return self._attr_entity_category

    @property
    def has_entity_name(self) -> bool:
        return self._attr_has_entity_name


class EntityPlatformState(enum.Enum):
    NOT_ADDED = enum.auto()
    ADDED = enum.auto()


ent.Entity = Entity
ent.EntityPlatformState = EntityPlatformState

# --- components ------------------------------------------------------------- #
acp = mod("homeassistant.components.alarm_control_panel")


class AlarmControlPanelState(enum.StrEnum):
    DISARMED = "disarmed"
    ARMED_HOME = "armed_home"
    ARMED_AWAY = "armed_away"
    PENDING = "pending"
    ARMING = "arming"
    TRIGGERED = "triggered"


class CodeFormat(enum.StrEnum):
    TEXT = "text"
    NUMBER = "number"


class AlarmControlPanelEntityFeature(enum.IntFlag):
    ARM_HOME = 1
    ARM_AWAY = 2
    ARM_NIGHT = 4
    TRIGGER = 8


class AlarmControlPanelEntity(Entity):
    pass


acp.AlarmControlPanelEntity = AlarmControlPanelEntity
acp.AlarmControlPanelEntityFeature = AlarmControlPanelEntityFeature
acp.AlarmControlPanelState = AlarmControlPanelState
acp.CodeFormat = CodeFormat

bs = mod("homeassistant.components.binary_sensor")


class BinarySensorDeviceClass(enum.StrEnum):
    BATTERY = "battery"
    CO = "carbon_monoxide"
    CONNECTIVITY = "connectivity"
    DOOR = "door"
    GAS = "gas"
    MOTION = "motion"
    POWER = "power"
    SAFETY = "safety"
    SMOKE = "smoke"
    TAMPER = "tamper"
    WINDOW = "window"


class BinarySensorEntity(Entity):
    pass


bs.BinarySensorDeviceClass = BinarySensorDeviceClass
bs.BinarySensorEntity = BinarySensorEntity

sensor = mod("homeassistant.components.sensor")
switch = mod("homeassistant.components.switch")
button = mod("homeassistant.components.button")
diag = mod("homeassistant.components.diagnostics")


class SensorEntity(Entity):
    pass


class SwitchEntity(Entity):
    pass


class ButtonEntity(Entity):
    pass


sensor.SensorEntity = SensorEntity
switch.SwitchEntity = SwitchEntity
button.ButtonEntity = ButtonEntity


def async_redact_data(data, keys):
    return {k: ("**REDACTED**" if k in keys else v) for k, v in data.items()}


diag.async_redact_data = async_redact_data

# --------------------------------------------------------------------------- #
# Import the integration
# --------------------------------------------------------------------------- #
INTEGRATION = REPO / "custom_components"
sys.path.insert(0, str(INTEGRATION.parent))
import custom_components.crowipmodule as crow  # noqa: E402
from custom_components.crowipmodule import device as crow_device  # noqa: E402
from custom_components.crowipmodule import const as crow_const  # noqa: E402
from custom_components.crowipmodule import (  # noqa: E402
    alarm_control_panel,
    binary_sensor,
    button as crow_button,
    diagnostics,
    sensor as crow_sensor,
    switch as crow_switch,
)

# --------------------------------------------------------------------------- #
# Fake hass / entry
# --------------------------------------------------------------------------- #
class FakeLoop:
    def call_soon_threadsafe(self, func, *args):
        func(*args)


class FakeBus:
    def async_listen_once(self, event, action):
        return lambda: None


class FakeConfigEntries:
    def __init__(self) -> None:
        self.forwarded: list[tuple[str, tuple]] = []

    async def async_forward_entry_setups(self, entry, platforms):
        self.forwarded.append((entry.entry_id, tuple(platforms)))
        return True

    async def async_unload_platforms(self, entry, platforms):
        return True

    async def async_reload(self, entry_id):
        return True


class FakeHass:
    def __init__(self) -> None:
        self.loop = FakeLoop()
        self.bus = FakeBus()
        self.config_entries = FakeConfigEntries()
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class FakeEntry:
    def __init__(self, data, options) -> None:
        self.data = data
        self.options = options
        self.entry_id = "entry-1"
        self.title = "192.168.1.50"
        self.runtime_data = None

    def async_on_unload(self, func):
        pass

    def add_update_listener(self, listener):
        return lambda: None


DATA = {
    "host": "192.168.1.50",
    "port": 5002,
    "keepalive_interval": 300,
    "timeout": 10,
    "firmware_version": "Ver 2.10.3628 2017",
    "firmware_date": "Oct 20 09:48:43",
    "number_of_areas": 2,
    "number_of_zones": 4,
    "number_of_outputs": 2,
}
OPTIONS = {
    "areas": {
        "1": {"name": "House", "code": "1234", "code_arm_required": True},
        "2": {"name": "Garage", "code": "", "code_arm_required": True},
    },
    "outputs": {"1": {"name": "Gate"}, "2": {"name": "Siren"}},
    "zones": {
        "1": {"name": "Front Door", "type": "door"},
        "2": {"name": "Kitchen", "type": "motion"},
        "3": {"name": "Window", "type": "window"},
        "4": {"name": "Smoke", "type": "smoke"},
    },
}


async def main() -> None:
    hass = FakeHass()
    entry = FakeEntry(DATA, OPTIONS)

    print("== Integration setup ==")
    assert await crow.async_setup_entry(hass, entry) is True
    check("async_setup_entry returns True", True)
    check("runtime_data is set", entry.runtime_data is not None)
    check("hub device registered first", len(REGISTRY.created) == 1)
    check(
        "hub device has no via_device_id",
        "via_device_id" not in REGISTRY.created[0],
    )
    check(
        "hub configuration_url is valid",
        REGISTRY.created[0].get("configuration_url") == "http://192.168.1.50",
    )
    check(
        "hub sw_version carries firmware",
        REGISTRY.created[0].get("sw_version") == "Ver 2.10.3628 2017 (Oct 20 09:48:43)",
    )
    hub_id = entry.runtime_data.device_id
    check("runtime_data.device_id populated", hub_id == "device1")

    # ---------------------------------------------------------------- #
    print("\n== Platform setup ==")
    collected: list = []

    def collector(entities, *args):
        collected.extend(entities if isinstance(entities, (list, tuple)) else [entities])

    for module in (alarm_control_panel, binary_sensor, crow_button, crow_sensor, crow_switch):
        collected.clear()
        await module.async_setup_entry(hass, entry, collector)
        print(f"  {module.__name__.split('.')[-1]:20} -> {len(collected)} entities")

        for entity in collected:
            label = f"{type(entity).__name__}.device_info"
            info = entity.device_info
            check(f"{label} has no deprecated 'via_device'", "via_device" not in info)
            check(f"{label} has identifiers", bool(info.get("identifiers")))
            check(f"{label} has a name", bool(info.get("name")))
            if url := info.get("configuration_url"):
                from urllib.parse import urlparse

                parsed = urlparse(url)
                check(
                    f"{label} configuration_url valid ({url})",
                    parsed.scheme in ("http", "https", "homeassistant") and bool(parsed.hostname),
                )
            if info.get("via_device_id"):
                check(f"{label} via_device_id points at the hub", info["via_device_id"] == hub_id)

    # ---------------------------------------------------------------- #
    print("\n== Zone device grouping ==")
    # The platform registers a device per zone type before it links an entity to
    # it - do the same here so the fixture below can reference those devices.
    # The doors device is registered with the *other* type's name: a device keeps
    # the name it was created with and Home Assistant never renames it, which is
    # how a door zone ends up with a ``..._windows_...`` entity id.
    # The per-type devices that releases up to 2.1.4 created, as they still exist
    # in the device registry of an installation that has been through them.
    for legacy_identifier, legacy_name, zone_type in (
        ("crow_windows", "Crow Alarm Windows", "window"),
        ("crow_doors", "Crow Alarm Doors", "door"),
        ("crow_motion", "Crow Alarm Motion", "motion"),
    ):
        info = binary_sensor.zone_device_info(
            entry.runtime_data, "192.168.1.50", zone_type
        )
        info["name"] = legacy_name
        info["identifiers"] = {(crow_const.DOMAIN, legacy_identifier)}
        REGISTRY.async_get_or_create(config_entry_id=entry.entry_id, **info)

    # Registry state as it looks for such a user: the door zone 1 is still
    # registered on the windows device, the motion zone on the windows device too.
    ENTITY_REGISTRY.add(FakeRegistryEntry(
        "binary_sensor.crow_alarm_windows_front_door", "crow_zone_1",
        device_id=device_id_for_identifier("crow_windows"), object_id_base="Front Door",
    ))
    ENTITY_REGISTRY.add(FakeRegistryEntry(
        "binary_sensor.crow_alarm_windows_window", "crow_zone_3",
        device_id=device_id_for_identifier("crow_windows"), object_id_base="Window",
    ))
    ENTITY_REGISTRY.add(FakeRegistryEntry(
        "binary_sensor.meine_bewegung", "crow_zone_2",
        device_id=device_id_for_identifier("crow_windows"), object_id_base="Kitchen",
    ))

    collected.clear()
    await binary_sensor.async_setup_entry(hass, entry, collector)
    zones = [e for e in collected if type(e).__name__ == "CrowZoneSensor"]
    check("4 zone sensors created", len(zones) == 4)
    by_name = {e._attr_name: e for e in zones}
    check(
        "every zone is registered on the one Crow Alarm Sensors device",
        all(
            e.device_info["name"] == "Crow Alarm Sensors"
            and e.device_info["identifiers"] == {(crow_const.DOMAIN, "crow_sensors")}
            for e in zones
        ),
        str({e._attr_name: e.device_info["name"] for e in zones}),
    )
    check(
        "the zone type still decides the device class",
        by_name["Front Door"]._attr_device_class is BinarySensorDeviceClass.DOOR
        and by_name["Window"]._attr_device_class is BinarySensorDeviceClass.WINDOW
        and by_name["Kitchen"]._attr_device_class is BinarySensorDeviceClass.MOTION
        and by_name["Smoke"]._attr_device_class is BinarySensorDeviceClass.SMOKE,
    )
    check(
        "every zone type has a device class",
        set(crow_const.ZONE_TYPES) == set(binary_sensor._ZONE_DEVICE_CLASSES),
    )
    check(
        "an unknown zone type lands on the same device",
        binary_sensor.CrowZoneSensor(
            entry.runtime_data, "192.168.1.50", 9, "Odd", "banana"
        ).device_info["identifiers"]
        == {(crow_const.DOMAIN, crow_const.IDENTIFIER_ZONE)},
    )
    check(
        "zone devices carry via_device_id",
        all(e.device_info.get("via_device_id") == hub_id for e in zones),
    )
    check(
        "zone device classes are real enum members",
        by_name["Window"]._attr_device_class is BinarySensorDeviceClass.WINDOW
        and by_name["Front Door"]._attr_device_class is BinarySensorDeviceClass.DOOR,
    )
    check("zone entities do not poll", zones[0].should_poll is False)

    print("\n== Zone registry alignment ==")
    sensors_id = device_id_for_identifier("crow_sensors")
    for entity_id in (
        "binary_sensor.crow_alarm_windows_front_door",
        "binary_sensor.crow_alarm_windows_window",
        "binary_sensor.meine_bewegung",
    ):
        registry_entry = ENTITY_REGISTRY.async_get(entity_id)
        check(
            f"{entity_id} is moved onto the zone device",
            registry_entry is not None and registry_entry.device_id == sensors_id,
            str(registry_entry and registry_entry.device_id),
        )
    check(
        "entity ids are left untouched",
        ENTITY_REGISTRY.async_get("binary_sensor.crow_alarm_windows_front_door") is not None
        and ENTITY_REGISTRY.async_get("binary_sensor.meine_bewegung") is not None,
    )
    check(
        "the retired per-type devices are removed once empty",
        all(
            (crow_const.DOMAIN, identifier) not in REGISTRY.entries
            for identifier in crow_const.LEGACY_ZONE_IDENTIFIERS
        ),
        str([key for key in REGISTRY.entries if key[1].startswith("crow_")]),
    )

    print("\n== System status sensors ==")
    system = [e for e in collected if type(e).__name__ == "CrowSystemStatusSensor"]
    check("6 system sensors created", len(system) == 6)
    check(
        "system sensors live on the hub device",
        all(e.device_info["identifiers"] == {(crow_const.DOMAIN, crow_const.IDENTIFIER_HUB)} for e in system),
    )
    check(
        "system sensors are diagnostic",
        all(e.entity_category == EntityCategory.DIAGNOSTIC for e in system),
    )

    # ---------------------------------------------------------------- #
    print("\n== Alarm panel state machine ==")
    collected.clear()
    await alarm_control_panel.async_setup_entry(hass, entry, collector)
    check("2 alarm panels created", len(collected) == 2)
    panel = collected[0]
    check(
        "alarm_state property present",
        hasattr(panel, "alarm_state"),
    )
    check(
        "supported features = ARM_HOME|ARM_AWAY|TRIGGER",
        panel.supported_features
        == (
            AlarmControlPanelEntityFeature.ARM_HOME
            | AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.TRIGGER
        ),
    )
    check("code_format is numeric", panel.code_format is CodeFormat.NUMBER)
    check("code_arm_required False when a code is stored", panel.code_arm_required is False)
    check("unique_id is scoped to the entry", panel.unique_id.startswith("entry-1_"))

    controller = entry.runtime_data.controller
    cases = [
        ({"alarm": True}, AlarmControlPanelState.TRIGGERED),
        ({"armed": True}, AlarmControlPanelState.ARMED_AWAY),
        ({"stay_armed": True}, AlarmControlPanelState.ARMED_HOME),
        ({"exit_delay": True}, AlarmControlPanelState.ARMING),
        ({"stay_exit_delay": True}, AlarmControlPanelState.ARMING),
        ({"disarmed": True}, AlarmControlPanelState.DISARMED),
        ({}, None),
    ]
    for status, expected in cases:
        controller.area_state[1]["status"].update(
            {
                "alarm": False,
                "armed": False,
                "stay_armed": False,
                "disarmed": False,
                "exit_delay": False,
                "stay_exit_delay": False,
            }
        )
        controller.area_state[1]["status"].update(status)
        panel._info = controller.area_state[1]
        got = panel.alarm_state
        check(f"alarm_state({status or 'idle'}) -> {expected}", got == expected)

    # ---------------------------------------------------------------- #
    print("\n== Arm sequence ==")
    # Record the wire commands instead of writing to a (absent) socket. send_keypress
    # already appends the Enter key, so "KEYS 1234E" is "type 1234, press Enter".
    calls: list[str] = []
    controller.arm_away = lambda: calls.append("ARM")
    controller.arm_stay = lambda: calls.append("STAY")
    controller.send_keypress = lambda code: calls.append(f"KEYS {code}E")
    controller.disarm = lambda code: calls.append(f"DISARM {code}")

    panel_a, panel_b = collected[0], collected[1]  # area 1 has code 1234, area 2 has none

    def make_panel(sequence: str, code: str = "1234"):
        return alarm_control_panel.CrowAlarmPanel(
            controller, "192.168.1.50", "entry-1", 1, "House", code, True,
            "Ver 2.10.3628 2017", arm_sequence=sequence,
        )

    check(
        "panel defaults to command_then_keypad",
        panel_a._arm_sequence == "command_then_keypad",
        str(panel_a._arm_sequence),
    )

    calls.clear()
    await panel_a.async_alarm_arm_away()
    check("arm away (keypad mode) -> ARM then KEYS 1234E", calls == ["ARM", "KEYS 1234E"], str(calls))

    calls.clear()
    await panel_a.async_alarm_arm_home()
    check("arm home (keypad mode) -> STAY then KEYS 1234E", calls == ["STAY", "KEYS 1234E"], str(calls))

    calls.clear()
    await panel_a.async_alarm_arm_away("4321")
    check("a supplied code overrides the stored code", calls == ["ARM", "KEYS 4321E"], str(calls))

    command_only = make_panel("command_only")
    calls.clear()
    await command_only.async_alarm_arm_away()
    await command_only.async_alarm_arm_home()
    check("command_only sends the bare arm commands", calls == ["ARM", "STAY"], str(calls))

    calls.clear()
    await panel_b.async_alarm_arm_away()
    check("no code configured -> command only, no keypress", calls == ["ARM"], str(calls))

    calls.clear()
    await panel_a.async_alarm_disarm()
    check("disarm uses the stored code", calls == ["DISARM 1234"], str(calls))

    calls.clear()
    await panel_a.async_alarm_disarm("9876")
    check("disarm uses the supplied code", calls == ["DISARM 9876"], str(calls))

    calls.clear()
    await panel_b.async_alarm_disarm()
    check("disarm without any code sends nothing", calls == [], str(calls))

    # The platform (not just the constructor) must resolve the configured mode.
    entry.data["arm_sequence"] = "command_only"
    collected.clear()
    await alarm_control_panel.async_setup_entry(hass, entry, collector)
    check(
        "platform reads arm_sequence from entry.data",
        collected[0]._arm_sequence == "command_only",
        str(collected[0]._arm_sequence),
    )

    entry.options["arm_sequence"] = "command_then_keypad"
    collected.clear()
    await alarm_control_panel.async_setup_entry(hass, entry, collector)
    check(
        "entry.options wins over entry.data",
        collected[0]._arm_sequence == "command_then_keypad",
        str(collected[0]._arm_sequence),
    )

    del entry.data["arm_sequence"]
    del entry.options["arm_sequence"]
    collected.clear()
    await alarm_control_panel.async_setup_entry(hass, entry, collector)
    check(
        "falls back to the default arm sequence",
        collected[0]._arm_sequence == crow_const.DEFAULT_ARM_SEQUENCE,
        str(collected[0]._arm_sequence),
    )

    print("\n== Switch + button + sensor wiring ==")
    collected.clear()
    await crow_switch.async_setup_entry(hass, entry, collector)
    check("2 outputs created", len(collected) == 2)
    check("switch device_info has no via_device", "via_device" not in collected[0].device_info)

    collected.clear()
    await crow_switch.async_setup_entry(hass, entry, collector)
    out = collected[0]
    sent: list[str] = []
    controller.command_output = lambda num: sent.append(num)

    async def just_return(coro):
        return coro

    out.hass = types.SimpleNamespace(async_add_executor_job=None)
    await out.async_turn_on()
    check("turn_on sends OO command for output 1", sent == ["1"])
    sent.clear()
    await out.async_turn_on()
    check("turn_on is idempotent (no repeat command)", sent == [])
    await out.async_turn_off()
    check("turn_off sends OO command again", sent == ["1"])

    collected.clear()
    await crow_button.async_setup_entry(hass, entry, collector)
    check("3 buttons created (chime + 2 relays)", len(collected) == 3)
    check(
        "relay button unique ids stable",
        {e.unique_id for e in collected} == {"crow_toggle_chime", "crow_relay_1", "crow_relay_2"},
    )

    collected.clear()
    await crow_sensor.async_setup_entry(hass, entry, collector)
    check("1 system sensor + 2 area sensors", len(collected) == 3)

    # ---------------------------------------------------------------- #
    print("\n== Diagnostics ==")
    controller.system_state["status"]["alarm"] = False
    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
    check("diagnostics redacts the host", result["entry_data"]["host"] == "**REDACTED**")
    check(
        "diagnostics redacts area codes",
        result["options"]["areas"]["1"]["code"] == "**REDACTED**",
    )
    check("diagnostics reports connection state", result["connected"] is False)
    check("diagnostics includes zones", "zones" in result["state"])

    report = result["zone_registry"]
    check("diagnostics includes the zone registry report", isinstance(report, dict), str(report))
    check(
        "diagnostics reports the device the zones live on",
        report["1"]["expected_device"] == "Crow Alarm Sensors"
        and report["1"]["expected_device_identifier"] == "crow_sensors",
        str(report["1"]),
    )
    check(
        "diagnostics reports the entity and the device it really sits on",
        report["1"]["entity_id"] == "binary_sensor.crow_alarm_windows_front_door"
        and report["1"]["device_identifiers"] == ["crow_sensors"],
        str(report["1"]),
    )
    check(
        "diagnostics reports a zone that has no entity yet",
        "entity_id" not in report["4"],
        str(report["4"]),
    )

    # ---------------------------------------------------------------- #
    print("\n== configuration_url hardening ==")
    check("bare IPv4 normalised", crow_device.configuration_url("192.168.1.50") == "http://192.168.1.50")
    check("scheme preserved", crow_device.configuration_url("https://crow.local") == "https://crow.local")
    check("hostname accepted", crow_device.configuration_url("crow.local") == "http://crow.local")
    check("empty rejected", crow_device.configuration_url("") is None)
    check("None rejected", crow_device.configuration_url(None) is None)
    check("non-http scheme rejected", crow_device.configuration_url("ftp://crow.local") is None)
    check(
        "path-only rejected",
        crow_device.configuration_url("/dev/null") is None,
    )

    # ---------------------------------------------------------------- #
    print("\n== Unload ==")
    assert await crow.async_unload_entry(hass, entry) is True
    check("async_unload_entry returns True", True)


if __name__ == "__main__":
    asyncio.run(main())
    print("\n" + "=" * 40)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for item in FAILURES:
            print(f"  - {item}")
        sys.exit(1)
    print("ALL CHECKS PASSED")
