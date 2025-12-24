"""Support for Crow IP Module switches (Outputs & Relays)."""
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    SIGNAL_OUTPUT_UPDATE,
    CONF_OUTPUTS,
)

_LOGGER = logging.getLogger(__name__)

"""Support for Crow IP Module switches (Outputs)."""
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import CONF_HOST

from .const import (
    DOMAIN,
    SIGNAL_OUTPUT_UPDATE,
    CONF_OUTPUTS,
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
    
    entities = []
    configured_outputs = options.get(CONF_OUTPUTS, {})
    
    # STRICT LIMIT: Only create entities for Output 1 and 2.
    for i in range(1, 3):
        out_str = str(i)
        if out_str in configured_outputs:
             data = configured_outputs[out_str]
             name = data.get("name", f"Output {i}")
             if name:
                 entities.append(CrowOutput(controller, host, i, name))

    async_add_entities(entities)


class CrowBaseSwitch(SwitchEntity):
    _attr_has_entity_name = True 

    def __init__(self, controller, host):
        self._controller = controller
        self._host = host

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            configuration_url=f"http://{self._host}",
        )


class CrowOutput(CrowBaseSwitch):
    def __init__(self, controller, host, output_number, output_name) -> None:
        super().__init__(controller, host)
        self._output_number = output_number
        self._attr_name = output_name
        self._attr_unique_id = f"crow_output_{output_number}"
        self._is_on = False
        
        if self._output_number in self._controller.output_state:
             self._is_on = self._controller.output_state[self._output_number].get("status", {}).get("open", False)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_OUTPUT_UPDATE, self._update_callback)
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._controller.command_output(str(self._output_number))
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._controller.command_output(str(self._output_number))
        self._is_on = False
        self.async_write_ha_state()

    @callback
    def _update_callback(self, output) -> None:
        if output is None or int(output) == self._output_number:
            if self._output_number in self._controller.output_state:
                new_state = self._controller.output_state[self._output_number]["status"]["open"]
                if self._is_on != new_state:
                    self._is_on = new_state
                    self.async_write_ha_state()
async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Crow IP Module switches."""
    controller = hass.data[DOMAIN][entry.entry_id]
    options = entry.options
    host = entry.data[CONF_HOST] # FIX
    
    entities = []

    configured_outputs = options.get(CONF_OUTPUTS, {})
    
    if not configured_outputs:
         configured_outputs = {
             "3": {"name": "Modem"},
             "4": {"name": "Gatewayrouter"}
         }

    for output_num_str, output_data in configured_outputs.items():
        output_num = int(output_num_str)
        name = output_data.get("name", f"Output {output_num}")
        entities.append(CrowOutput(controller, host, output_num, name))

    for relay_num in range(1, 3):
        entities.append(CrowRelay(controller, host, relay_num))

    async_add_entities(entities)


class CrowBaseSwitch(SwitchEntity):
    _attr_has_entity_name = True 

    def __init__(self, controller, host):
        self._controller = controller
        self._host = host # FIX

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "crow_alarm_panel")},
            name="Crow Alarm System",
            manufacturer="Crow/AAP",
            model="IP Module",
            configuration_url=f"http://{self._host}", # FIX
        )


class CrowOutput(CrowBaseSwitch):
    def __init__(self, controller, host, output_number, output_name) -> None:
        super().__init__(controller, host)
        self._output_number = output_number
        self._attr_name = output_name
        self._attr_unique_id = f"crow_output_{output_number}"
        self._is_on = False
        
        # Initial State Check with Safety
        if self._output_number in self._controller.output_state:
             self._is_on = self._controller.output_state[self._output_number].get("status", {}).get("open", False)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_OUTPUT_UPDATE, self._update_callback)
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._controller.command_output(str(self._output_number))
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._controller.command_output(str(self._output_number))
        self._is_on = False
        self.async_write_ha_state()

    @callback
    def _update_callback(self, output) -> None:
        if output is None or int(output) == self._output_number:
            if self._output_number in self._controller.output_state:
                new_state = self._controller.output_state[self._output_number]["status"]["open"]
                if self._is_on != new_state:
                    self._is_on = new_state
                    self.async_write_ha_state()


class CrowRelay(CrowBaseSwitch):
    def __init__(self, controller, host, relay_number) -> None:
        super().__init__(controller, host)
        self._relay_number = relay_number
        self._attr_name = f"Relay {relay_number}"
        self._attr_unique_id = f"crow_relay_{relay_number}"
        self._attr_icon = "mdi:electric-switch"

    @property
    def is_on(self) -> bool:
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._controller.relay_on(self._relay_number)
        
    async def async_turn_off(self, **kwargs: Any) -> None:
        pass
