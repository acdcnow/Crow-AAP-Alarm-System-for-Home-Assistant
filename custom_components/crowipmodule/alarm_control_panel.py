"""Support for Crow IP Module Alarm Control Panel."""
import logging

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_AREA_UPDATE,
    SIGNAL_KEYPAD_UPDATE,
    CONF_AREAS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Crow Alarm Panels from a config entry."""
    controller = hass.data[DOMAIN][entry.entry_id]
    options = entry.options
    
    # Konfigurierte Areas laden (oder Standardwerte nutzen)
    configured_areas = options.get(CONF_AREAS, {})
    
    devices = []
    
    # Falls noch keine Areas konfiguriert sind (initialer Start), Standards setzen
    if not configured_areas:
        # Standard: Area 1 und 2
        configured_areas = {
            "1": {"name": "Area A", "code": "", "code_arm_required": True},
            "2": {"name": "Area B", "code": "", "code_arm_required": True}
        }

    for area_num_str, area_data in configured_areas.items():
        area_num = int(area_num_str)
        # Sicherstellen, dass Area 1 oder 2 ist (Hardware Limitierung meistens)
        if area_num in [1, 2]:
            devices.append(CrowAlarmPanel(
                controller, 
                area_num, 
                area_data.get("name", f"Area {area_num}"),
                area_data.get("code", ""),
                area_data.get("code_arm_required", True)
            ))

    async_add_entities(devices)


class CrowAlarmPanel(AlarmControlPanelEntity):
    """Representation of a Crow Alarm Area."""
    
    _attr_has_entity_name = True  # WICHTIG für HA 2025
    _attr_name = None             # Name kommt vom Init (z.B. "Area A")

    def __init__(self, controller, area_number, name, code, code_required) -> None:
        """Initialize the alarm panel."""
        self._controller = controller
        self._area_number_int = area_number
        self._area_number = "A" if area_number == 1 else "B"
        
        self._attr_name = name
        self._attr_unique_id = f"crow_area_{area_number}"
        
        self._code = code
        self._code_required = code_required
        
        # Initialen State laden falls verfügbar
        if area_number in controller.area_state:
            self._info = controller.area_state[area_number]
        else:
            self._info = {"status": {}} # Fallback

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to link all entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            configuration_url=f"http://{self._controller.ip}",
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_AREA_UPDATE, self._update_callback)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_KEYPAD_UPDATE, self._update_callback)
        )

    @callback
    def _update_callback(self, area) -> None:
        """Update Home Assistant state, if needed."""
        # Prüfen ob das Update für diese Area ist
        if area is None or area == self._area_number:
            # Update info reference
            self._info = self._controller.area_state[self._area_number_int]
            self.async_write_ha_state()

    @property
    def code_format(self) -> CodeFormat | None:
        """Regex for code format or None if no code is required."""
        # Wenn ein Code fest hinterlegt ist, benötigt die UI keinen Code
        if self._code:
            return None
        return CodeFormat.NUMBER

    @property
    def code_arm_required(self) -> bool:
        """Whether the code is required for arm actions."""
        return self._code_required

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the state of the device."""
        status = self._info.get("status", {})

        if status.get("alarm"):
            return AlarmControlPanelState.TRIGGERED
        if status.get("armed"):
            return AlarmControlPanelState.ARMED_AWAY
        if status.get("stay_armed"):
            return AlarmControlPanelState.ARMED_HOME
        if status.get("exit_delay") or status.get("stay_exit_delay"):
            return AlarmControlPanelState.PENDING
        if status.get("disarmed"):
            return AlarmControlPanelState.DISARMED
            
        return None

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        """Return the list of supported features."""
        return (
            AlarmControlPanelEntityFeature.ARM_HOME
            | AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.TRIGGER
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        code_to_use = str(code) if code else str(self._code)
        self._controller.disarm(code_to_use)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        self._controller.arm_stay()
        # Code wird bei Crow oft nach dem Befehl gesendet
        code_to_use = str(self._code)
        if code:
             code_to_use = str(code)
        
        if code_to_use:
            self._controller.send_keypress(code_to_use)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        self._controller.arm_away()
        code_to_use = str(code) if code else str(self._code)
        
        if code_to_use:
            self._controller.send_keypress(code_to_use)

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        """Alarm trigger command. Will be used to trigger a panic alarm."""
        self._controller.panic_alarm("")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._info.get("status", {})
