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
IDENTIFIER_WINDOWS = "crow_windows"
IDENTIFIER_DOORS = "crow_doors"
IDENTIFIER_SENSORS = "crow_sensors"
DEVICE_NAME = "Crow Alarm System"
DEVICE_NAME_WINDOWS = "Crow Alarm Windows"
DEVICE_NAME_DOORS = "Crow Alarm Doors"
DEVICE_NAME_SENSORS = "Crow Alarm Sensors"

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
