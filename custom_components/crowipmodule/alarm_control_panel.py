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
    SIGNAL_KEYPAD_UPDATE,
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
        if area_num in [1, 2]:
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
        self._area_number = "A" if area_number == 1 else "B"
        
        self._attr_name = name
        self._attr_unique_id = f"crow_area_{area_number}"
        self._attr_icon = "mdi:shield-home"
        
        self._code = code
        # Info: code_required kommt aus der Config, wir nutzen es unten in der Property
        self._code_arm_required_config = code_required
        
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
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_KEYPAD_UPDATE, self._update_callback)
        )

    @callback
    def _update_callback(self, area) -> None:
        if area is None or area == self._area_number:
            if self._area_number_int in self._controller.area_state:
                self._info = self._controller.area_state[self._area_number_int]
            self.async_write_ha_state()

    @property
    def code_format(self) -> CodeFormat | None:
        """Zeige IMMER das Keypad an."""
        return CodeFormat.NUMBER

    @property
    def code_arm_required(self) -> bool:
        """
        Entscheidet, ob Home Assistant eine Eingabe erzwingt.
        WICHTIG: Wenn ein Standard-Code (_code) hinterlegt ist, setzen wir dies auf False.
        Das erlaubt dem Nutzer, das Feld LEER zu lassen (dann wird _code genommen)
        ODER etwas einzutippen (dann wird das Eingetippte genommen).
        """
        if self._code:
            return False
        return self._code_arm_required_config

    @property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        return (
            AlarmControlPanelEntityFeature.ARM_HOME
            | AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.TRIGGER
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Disarm command."""
        # Logik aus original file: Wenn code da, nimm code. Sonst self._code.
        code_to_use = str(code) if code else str(self._code)
        self._controller.disarm(code_to_use)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Arm Stay command."""
        # Logik aus original file: Erst arm_stay(), dann Code senden.
        self._controller.arm_stay()
        
        code_to_use = str(code) if code else str(self._code)
        if code_to_use:
            self._controller.send_keypress(code_to_use)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Arm Away command."""
        # Logik aus original file: Erst arm_away(), dann Code senden.
        self._controller.arm_away()
        
        code_to_use = str(code) if code else str(self._code)
        if code_to_use:
            self._controller.send_keypress(code_to_use)

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        self._controller.panic_alarm("")

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        status = self._info.get("status", {})
        if status.get("alarm"): return AlarmControlPanelState.TRIGGERED
        if status.get("armed"): return AlarmControlPanelState.ARMED_AWAY
        if status.get("stay_armed"): return AlarmControlPanelState.ARMED_HOME
        if status.get("exit_delay") or status.get("stay_exit_delay"): return AlarmControlPanelState.PENDING
        if status.get("disarmed"): return AlarmControlPanelState.DISARMED
        return None
    
    @property
    def extra_state_attributes(self):
        return self._info.get("status", {})
