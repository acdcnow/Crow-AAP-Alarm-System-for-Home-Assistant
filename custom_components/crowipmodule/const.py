"""Constants for the Crow IP Module integration."""

DOMAIN = "crowipmodule"

# Configuration Keys
CONF_KEEP_ALIVE = "keepalive_interval"
CONF_AREAS = "areas"
CONF_ZONES = "zones"
CONF_OUTPUTS = "outputs"
CONF_FW_VERSION = "firmware_version"
CONF_FW_DATE = "firmware_date"

# Arming
# There is no single "arm with code" command in the Crow protocol. Depending on the
# panel firmware and how it is programmed, either the bare ARM/STAY command completes
# the arming, or the panel then waits for the user code followed by the Enter key.
# Which one applies is a per-entry option.
CONF_ARM_SEQUENCE = "arm_sequence"
ARM_SEQUENCE_COMMAND_ONLY = "command_only"
ARM_SEQUENCE_COMMAND_THEN_KEYPAD = "command_then_keypad"
ARM_SEQUENCES = [ARM_SEQUENCE_COMMAND_ONLY, ARM_SEQUENCE_COMMAND_THEN_KEYPAD]
# 2.0.0 and earlier always sent the code after the arm command, so that behaviour stays
# the default. Panels that arm on the bare command should select ARM_SEQUENCE_COMMAND_ONLY,
# because there the code + Enter is interpreted as a disarm.
DEFAULT_ARM_SEQUENCE = ARM_SEQUENCE_COMMAND_THEN_KEYPAD

# Firmware Profiles (Version -> Date)
FIRMWARE_PROFILES = {
    "Ver 2.10.3628 2017": "Oct 20 09:48:43",
    "unsupported": "unknown"
}

# Defaults
DEFAULT_FW_VERSION = "Ver 2.10.3628 2017"
DEFAULT_FW_DATE = "Oct 20 09:48:43"

# Dynamic Configuration Keys
CONF_NUM_AREAS = "number_of_areas"
CONF_NUM_ZONES = "number_of_zones"
CONF_NUM_OUTPUTS = "number_of_outputs"

# Limits
MAX_AREAS = 2
MAX_ZONES = 16 
MAX_OUTPUTS = 8

DEFAULT_NUM_AREAS = 2
DEFAULT_NUM_ZONES = 7
DEFAULT_NUM_OUTPUTS = 2

# Defaults
DEFAULT_PORT = 5002
DEFAULT_TIMEOUT = 10
DEFAULT_KEEPALIVE = 300

# Device registry
# NOTE: the identifier strings are part of the stored registry and must not be
# changed, otherwise every existing installation would get a duplicate device.
MANUFACTURER = "Crow/AAP"
MODEL_IP_MODULE = "IP Module"
MODEL_IP_MODULE_ZONE = "IP Module Zone"
IDENTIFIER_HUB = "crow_alarm_panel"
DEVICE_NAME = "Crow Alarm System"

# The types a zone can be configured as (`options["zones"][n]["type"]`). The
# order is the order of the dropdown in the config and options flow.
ZONE_TYPES = [
    "window", "motion", "door", "smoke", "gas", "co", "tamper", "safety"
]

# The zone entities all live on one device. The zone *type* still decides the
# binary-sensor device class (the icon in the UI), but it no longer decides which
# device the entity is registered on: Home Assistant only links an entity to a
# device when it is registered for the first time, so a zone that was re-typed
# afterwards could otherwise stay on the device of its former type.
IDENTIFIER_ZONE = "crow_sensors"
DEVICE_NAME_ZONE = "Crow Alarm Sensors"

# Identifiers of the per-type zone devices that releases up to 2.1.4 created.
# They are removed again once nothing is left on them.
LEGACY_ZONE_IDENTIFIERS = (
    "crow_windows",
    "crow_doors",
    "crow_motion",
    "crow_smoke",
    "crow_gas",
    "crow_co",
    "crow_tamper",
    "crow_safety",
)


def zone_device(zone_type: str | None = None) -> tuple[str, str]:
    """Return the ``(identifier, name)`` of the device the zones live on.

    Single source of truth for the mapping; used by the binary-sensor platform
    and by the diagnostics report. ``zone_type`` is still accepted (and ignored)
    so the call sites read the same as when the type chose the device.
    """
    return IDENTIFIER_ZONE, DEVICE_NAME_ZONE

# Signals
SIGNAL_ZONE_UPDATE = "crowipmodule.zones_updated"
SIGNAL_AREA_UPDATE = "crowipmodule.areas_updated"
SIGNAL_SYSTEM_UPDATE = "crowipmodule.system_updated"
SIGNAL_OUTPUT_UPDATE = "crowipmodule.output_updated"
SIGNAL_KEYPAD_UPDATE = "crowipmodule.keypad_updated"
SIGNAL_CONNECTION_UPDATE = "crowipmodule.connection_updated"

# System status sensors keys
CONF_OBJ_MAINS = "mains"
CONF_OBJ_BATTERY = "battery"
CONF_OBJ_TAMPER = "tamper"
CONF_OBJ_LINE = "line"
CONF_OBJ_DIALLER = "dialler"
CONF_OBJ_ZONE_BATTERY = "zonebattery"
CONF_OBJ_FUSE = "fuse"
CONF_OBJ_PENDANT_BATTERY = "pendantbattery"
CONF_OBJ_CODE_TAMPER = "codetamper"
CONF_OBJ_READY = "ready"
