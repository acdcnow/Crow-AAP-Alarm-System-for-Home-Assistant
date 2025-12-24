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
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    SIGNAL_AREA_UPDATE,
    CONF_AREAS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    controller = hass.data[DOMAIN][entry.entry_id]
    options = entry.options
    host = entry.data[CONF_HOST]
    
    configured_areas = options.get(CONF_AREAS, {})
    
    devices = []
    if not configured_areas:
        configured_areas = {
            "1": {"name": "Area A", "code": "", "code_arm_required": True},
            "2": {"name": "Area B", "code": "", "code_arm_required": True}
        }

    for area_num_str, area_data in configured_areas.items():
        area_num = int(area_num_str)
        devices.append(CrowAlarmPanel(
            controller, host,
            area_num, 
            area_data.get("name", f"Area {area_num}"),
            area_data.get("code", ""),
            area_data.get("code_arm_required", True)
        ))

    async_add_entities(devices)


class CrowAlarmPanel(AlarmControlPanelEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, controller, host, area_number, name, code, code_required) -> None:
        self._controller = controller
        self._host = host
        self._area_number_int = area_number
        self._attr_name = name
        self._attr_unique_id = f"crow_area_{area_number}"
        self._attr_icon = "mdi:shield-home"
        
        self._code = code
        # Wir erzwingen True, damit das Keypad immer da ist für manuelle Eingabe
        self._code_arm_required_config = True 
        
        self._info = controller.area_state.get(area_number, {"status": {}})

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            configuration_url=f"http://{self._host}",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_AREA_UPDATE, self._update_callback)
        )

    @callback
    def _update_callback(self, area) -> None:
        if area is None or area == self._area_number_int:
            if self._area_number_int in self._controller.area_state:
                self._info = self._controller.area_state[self._area_number_int]
            self.async_write_ha_state()

    @property
    def code_format(self) -> CodeFormat | None:
        """Zeige immer das Zahlenfeld an."""
        return CodeFormat.NUMBER

    @property
    def code_arm_required(self) -> bool:
        """Code ist zwingend erforderlich."""
        return True

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        return (
            AlarmControlPanelEntityFeature.ARM_HOME
            | AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.ARM_CUSTOM_BYPASS # Für Bypass Support
            | AlarmControlPanelEntityFeature.TRIGGER
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Sende CODE + ENTER."""
        if not code: return
        _LOGGER.info(f"Panel: Disarming Area {self._area_number_int}")
        self._controller.disarm(code)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Sende CODE + STAY + ENTER."""
        if not code: return
        _LOGGER.info(f"Panel: Arming Home Area {self._area_number_int}")
        self._controller.arm_stay(code)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Sende CODE + ARM + ENTER."""
        if not code: return
        _LOGGER.info(f"Panel: Arming Away Area {self._area_number_int}")
        self._controller.arm_away(code)

    async def async_alarm_arm_custom_bypass(self, code: str | None = None) -> None:
        """Sende CODE + BYPASS + ENTER."""
        if not code: return
        _LOGGER.info(f"Panel: Bypassing Area {self._area_number_int}")
        self._controller.bypass(code)

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        self._controller.panic_alarm("")

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        status = self._info.get("status", {})
        
        if status.get("alarm"): return AlarmControlPanelState.TRIGGERED
        if status.get("exit_delay"): return AlarmControlPanelState.PENDING
        if status.get("stay_armed"): return AlarmControlPanelState.ARMED_HOME
        if status.get("armed"): return AlarmControlPanelState.ARMED_AWAY
        if status.get("disarmed") is True: return AlarmControlPanelState.DISARMED
        
        return AlarmControlPanelState.DISARMED
