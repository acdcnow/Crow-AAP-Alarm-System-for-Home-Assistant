"""Constants for the Crow IP Module integration."""

DOMAIN = "crowipmodule"
DATA_CRW = "crowipmodule"

CONF_KEEP_ALIVE = "keepalive_interval"
CONF_AREAS = "areas"
CONF_ZONES = "zones"
CONF_OUTPUTS = "outputs"

# System status sensors
CONF_OBJ_MAINS = "mains"
CONF_OBJ_BATTERY = "battery"
CONF_OBJ_TAMPER = "tamper"
CONF_OBJ_LINE = "line"
CONF_OBJ_DIALLER = "dialler"
CONF_OBJ_ZONE_BATTERY = "zonebattery"

DEFAULT_PORT = 5002
DEFAULT_TIMEOUT = 10
DEFAULT_KEEPALIVE = 60

SIGNAL_ZONE_UPDATE = "crowipmodule.zones_updated"
SIGNAL_AREA_UPDATE = "crowipmodule.areas_updated"
SIGNAL_SYSTEM_UPDATE = "crowipmodule.system_updated"
SIGNAL_OUTPUT_UPDATE = "crowipmodule.output_updated"
SIGNAL_KEYPAD_UPDATE = "crowipmodule.keypad_updated"
