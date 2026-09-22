"""Config flow for Crow IP Module integration."""
import logging
import socket

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT
from homeassistant.helpers import selector

from .const import (
    ARM_SEQUENCES,
    CONF_ARM_SEQUENCE,
    DEFAULT_ARM_SEQUENCE,
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DEFAULT_KEEPALIVE,
    CONF_KEEP_ALIVE,
    CONF_AREAS,
    CONF_ZONES,
    CONF_OUTPUTS,
    CONF_NUM_AREAS,
    CONF_NUM_ZONES,
    CONF_NUM_OUTPUTS,
    CONF_FW_VERSION,
    CONF_FW_DATE,
    FIRMWARE_PROFILES,
    DEFAULT_FW_VERSION,
    MAX_AREAS,
    MAX_ZONES,
    MAX_OUTPUTS,
    DEFAULT_NUM_AREAS,
    DEFAULT_NUM_ZONES,
    DEFAULT_NUM_OUTPUTS,
    DEFAULT_FW_DATE,
)

_LOGGER = logging.getLogger(__name__)

ZONE_TYPES = [
    "window", "motion", "door", "smoke", "gas", "co", "tamper", "safety"
]

PAGE_SIZE = 4


def _arm_sequence_selector() -> selector.SelectSelector:
    """Dropdown for how the panel is armed (see const.CONF_ARM_SEQUENCE).

    The option labels are translated through ``selector.arm_sequence.options`` in
    strings.json / translations.
    """
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=ARM_SEQUENCES,
            translation_key=CONF_ARM_SEQUENCE,
        )
    )


def _test_connection(host: str, port: int, timeout: float) -> bool:
    """Blocking TCP connect check. Run in the executor."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class CrowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crow IP Module."""

    VERSION = 1

    def __init__(self):
        self._data = {}
        self._options = {}
        self._zone_page = 0

    async def async_step_user(self, user_input=None):
        """Step 1: Connection details and counts."""
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            timeout = user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

            unique_id = f"{host}_{port}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            connected = await self.hass.async_add_executor_job(
                _test_connection, host, port, timeout
            )
            if not connected:
                errors["base"] = "cannot_connect"
            else:
                self._data = user_input

                selected_version = user_input[CONF_FW_VERSION]
                self._data[CONF_FW_DATE] = FIRMWARE_PROFILES.get(selected_version, "unknown")

                self._options[CONF_AREAS] = {}
                self._options[CONF_OUTPUTS] = {}
                self._options[CONF_ZONES] = {}

                return await self.async_step_areas()

        fw_options = list(FIRMWARE_PROFILES.keys())

        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Optional(CONF_KEEP_ALIVE, default=DEFAULT_KEEPALIVE): int,
            vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
            
            vol.Required(CONF_FW_VERSION, default=DEFAULT_FW_VERSION): vol.In(fw_options),

            vol.Required(CONF_ARM_SEQUENCE, default=DEFAULT_ARM_SEQUENCE): _arm_sequence_selector(),

            vol.Required(CONF_NUM_AREAS, default=DEFAULT_NUM_AREAS): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_AREAS)),
            vol.Required(CONF_NUM_OUTPUTS, default=DEFAULT_NUM_OUTPUTS): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_OUTPUTS)),
            vol.Required(CONF_NUM_ZONES, default=DEFAULT_NUM_ZONES): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_ZONES)),
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_areas(self, user_input=None):
        count = self._data.get(CONF_NUM_AREAS, DEFAULT_NUM_AREAS)
        
        if user_input is not None:
            areas_config = {}
            for i in range(1, count + 1):
                areas_config[str(i)] = {
                    "name": user_input.get(f"area_{i}_name"), 
                    "code": user_input.get(f"area_{i}_code", ""), 
                    "code_arm_required": True
                }
            self._options[CONF_AREAS] = areas_config
            return await self.async_step_outputs()

        schema = {}
        for i in range(1, count + 1):
            schema[vol.Required(f"area_{i}_name", default=f"Area {i}")] = str
            schema[vol.Optional(f"area_{i}_code", default="")] = str

        return self.async_show_form(step_id="areas", data_schema=vol.Schema(schema))

    async def async_step_outputs(self, user_input=None):
        count = self._data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS)

        if count == 0:
            self._options[CONF_OUTPUTS] = {}
            self._zone_page = 0
            return await self.async_step_zones()

        if user_input is not None:
            outputs_config = {}
            for i in range(1, count + 1):
                name = user_input.get(f"output_{i}_name")
                if name:
                    outputs_config[str(i)] = {"name": name}
            
            self._options[CONF_OUTPUTS] = outputs_config
            self._zone_page = 0
            return await self.async_step_zones()

        schema = {}
        for i in range(1, count + 1):
            default_name = f"Output {i}"
            schema[vol.Optional(f"output_{i}_name", description={"suggested_value": default_name})] = str

        return self.async_show_form(step_id="outputs", data_schema=vol.Schema(schema))

    async def async_step_zones(self, user_input=None):
        count = self._data.get(CONF_NUM_ZONES, DEFAULT_NUM_ZONES)
        
        if user_input is not None:
            for key, value in user_input.items():
                if key.startswith("zone_") and key.endswith("_name"):
                    idx = key.split("_")[1]
                    if idx not in self._options[CONF_ZONES]:
                        self._options[CONF_ZONES][idx] = {}
                    self._options[CONF_ZONES][idx]["name"] = value
                elif key.startswith("zone_") and key.endswith("_type"):
                    idx = key.split("_")[1]
                    if idx not in self._options[CONF_ZONES]:
                        self._options[CONF_ZONES][idx] = {}
                    self._options[CONF_ZONES][idx]["type"] = value
            self._zone_page += 1

        start_idx = self._zone_page * PAGE_SIZE + 1
        if start_idx > count:
            return self.async_create_entry(
                title=self._data[CONF_HOST],
                data=self._data,
                options=self._options
            )

        end_idx = min(start_idx + PAGE_SIZE - 1, count)
        schema = {}
        for i in range(start_idx, end_idx + 1):
            schema[vol.Optional(f"zone_{i}_name")] = str
            schema[vol.Optional(f"zone_{i}_type", default="window")] = vol.In(ZONE_TYPES)

        return self.async_show_form(step_id="zones", data_schema=vol.Schema(schema))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CrowOptionsFlowHandler()


class CrowOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self):
        self._temp_data = {}
        self._temp_options = {}
        self._zone_page = 0

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self._temp_data = user_input
            
            # Refresh the firmware build date when the version changed.
            new_version = user_input.get(CONF_FW_VERSION)
            if new_version:
                self._temp_data[CONF_FW_DATE] = FIRMWARE_PROFILES.get(new_version, "unknown")
            
            return await self.async_step_areas()

        data = self.config_entry.data
        options = self.config_entry.options
        
        c_areas = data.get(CONF_NUM_AREAS, len(options.get(CONF_AREAS, {})) or DEFAULT_NUM_AREAS)
        c_zones = data.get(CONF_NUM_ZONES, len(options.get(CONF_ZONES, {})) or DEFAULT_NUM_ZONES)
        c_outputs = data.get(CONF_NUM_OUTPUTS, len(options.get(CONF_OUTPUTS, {})) or DEFAULT_NUM_OUTPUTS)
        
        current_fw = data.get(CONF_FW_VERSION, DEFAULT_FW_VERSION)
        current_arm_sequence = data.get(CONF_ARM_SEQUENCE, DEFAULT_ARM_SEQUENCE)
        fw_options = list(FIRMWARE_PROFILES.keys())

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=data.get(CONF_HOST)): str,
            vol.Optional(CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Optional(CONF_KEEP_ALIVE, default=data.get(CONF_KEEP_ALIVE, DEFAULT_KEEPALIVE)): int,
            vol.Optional(CONF_TIMEOUT, default=data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)): int,
            
            vol.Required(CONF_FW_VERSION, default=current_fw): vol.In(fw_options),

            vol.Required(CONF_ARM_SEQUENCE, default=current_arm_sequence): _arm_sequence_selector(),

            vol.Required(CONF_NUM_AREAS, default=c_areas): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_AREAS)),
            vol.Required(CONF_NUM_OUTPUTS, default=c_outputs): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_OUTPUTS)),
            vol.Required(CONF_NUM_ZONES, default=c_zones): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_ZONES)),
        })

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_areas(self, user_input=None):
        count = self._temp_data.get(CONF_NUM_AREAS, DEFAULT_NUM_AREAS)
        if user_input is not None:
            self._temp_options[CONF_AREAS] = {}
            for i in range(1, count + 1):
                self._temp_options[CONF_AREAS][str(i)] = {
                    "name": user_input.get(f"area_{i}_name"),
                    "code": user_input.get(f"area_{i}_code", ""),
                    "code_arm_required": True
                }
            return await self.async_step_outputs()

        existing = self.config_entry.options.get(CONF_AREAS, {})
        schema = {}
        for i in range(1, count + 1):
            d = existing.get(str(i), {})
            schema[vol.Optional(f"area_{i}_name", default=d.get("name", f"Area {i}"))] = str
            schema[vol.Optional(f"area_{i}_code", default=d.get("code", ""))] = str
        return self.async_show_form(step_id="areas", data_schema=vol.Schema(schema))

    async def async_step_outputs(self, user_input=None):
        count = self._temp_data.get(CONF_NUM_OUTPUTS, DEFAULT_NUM_OUTPUTS)

        if count == 0:
            self._temp_options[CONF_OUTPUTS] = {}
            self._zone_page = 0
            self._temp_options[CONF_ZONES] = {}
            return await self.async_step_zones()

        if user_input is not None:
            self._temp_options[CONF_OUTPUTS] = {}
            for i in range(1, count + 1):
                name = user_input.get(f"output_{i}_name")
                if name:
                    self._temp_options[CONF_OUTPUTS][str(i)] = {"name": name}
            
            self._zone_page = 0
            self._temp_options[CONF_ZONES] = {}
            return await self.async_step_zones()

        existing = self.config_entry.options.get(CONF_OUTPUTS, {})
        schema = {}
        for i in range(1, count + 1):
            d = existing.get(str(i), {})
            default = d.get("name", "")
            if not default: default = f"Output {i}"
            schema[vol.Optional(f"output_{i}_name", description={"suggested_value": default})] = str
        return self.async_show_form(step_id="outputs", data_schema=vol.Schema(schema))

    async def async_step_zones(self, user_input=None):
        count = self._temp_data.get(CONF_NUM_ZONES, DEFAULT_NUM_ZONES)
        
        if user_input is not None:
            for key, value in user_input.items():
                if key.startswith("zone_") and key.endswith("_name"):
                    idx = key.split("_")[1]
                    if idx not in self._temp_options[CONF_ZONES]:
                        self._temp_options[CONF_ZONES][idx] = {}
                    self._temp_options[CONF_ZONES][idx]["name"] = value
                elif key.startswith("zone_") and key.endswith("_type"):
                    idx = key.split("_")[1]
                    if idx not in self._temp_options[CONF_ZONES]:
                        self._temp_options[CONF_ZONES][idx] = {}
                    self._temp_options[CONF_ZONES][idx]["type"] = value
            self._zone_page += 1

        start_idx = self._zone_page * PAGE_SIZE + 1
        
        if start_idx > count:
            new_data = self.config_entry.data.copy()
            new_data.update(self._temp_data)
            # Only update entry.data here; options are saved by async_create_entry below.
            # Passing options= here AND data={} to async_create_entry would wipe the options.
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            # async_create_entry saves self._temp_options as the new options and
            # automatically triggers update_listener → reload. No manual reload needed.
            return self.async_create_entry(title="", data=self._temp_options)

        existing_zones = self.config_entry.options.get(CONF_ZONES, {})
        end_idx = min(start_idx + PAGE_SIZE - 1, count)
        
        schema = {}
        for i in range(start_idx, end_idx + 1):
            d = existing_zones.get(str(i), {})
            current_name = d.get("name", "")
            current_type = d.get("type", "window") 
            
            schema[vol.Optional(f"zone_{i}_name", description={"suggested_value": current_name})] = str
            schema[vol.Optional(f"zone_{i}_type", default=current_type)] = vol.In(ZONE_TYPES)

        return self.async_show_form(step_id="zones", data_schema=vol.Schema(schema))
