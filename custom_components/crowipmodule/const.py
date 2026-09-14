"""Constants for the Crow IP Module integration."""

DOMAIN = "crowipmodule"

# Configuration Keys
CONF_KEEP_ALIVE = "keepalive_interval"
CONF_AREAS = "areas"
CONF_ZONES = "zones"
CONF_OUTPUTS = "outputs"
CONF_FW_VERSION = "firmware_version"
CONF_FW_DATE = "firmware_date"

# Firmware Profiles (Version -> Date)
FIRMWARE_PROFILES = {
    "Ver 2.10.3628 2017": "Oct 20 09:48:43",
    "unsupported": "unknown"
}

# Defaults
DEFAULT_FW_VERSION = "Ver 2.10.3628 2017"
# WICHTIG: Diese Konstante fehlte und verursachte den ImportError
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
