"""Config flow for Crow IP Module integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT
from .const import DOMAIN, DEFAULT_PORT, DEFAULT_TIMEOUT, DEFAULT_KEEPALIVE, CONF_KEEP_ALIVE, CONF_AREAS, CONF_ZONES, CONF_OUTPUTS

_LOGGER = logging.getLogger(__name__)

ZONE_TYPES = ["motion", "door", "window", "smoke", "gas", "co", "tamper", "safety"]

class CrowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    def __init__(self):
        self.areas_config = {}
        self.outputs_config = {}
        self.zones_count = 0
        self.zones_config = {}

    async def async_step_user(self, user_input=None):
        return await self.async_step_areas()

    async def async_step_areas(self, user_input=None):
        if user_input is not None:
            self.areas_config = user_input
            return await self.async_step_outputs()
        schema = {}
        for i in range(1, 3):
            schema[vol.Optional(f"area_{i}_name", default=f"Area {i}")] = str
            schema[vol.Optional(f"area_{i}_code", default="")] = str
        return self.async_show_form(step_id="areas", data_schema=vol.Schema(schema))

    async def async_step_outputs(self, user_input=None):
        if user_input is not None:
            self.outputs_config = user_input
            return await self.async_step_zones_count()
        schema = {
            vol.Optional("output_1_name", description={"suggested_value": "Relay 1"}): str,
            vol.Optional("output_2_name", description={"suggested_value": "Relay 2"}): str,
        }
        return self.async_show_form(step_id="outputs", data_schema=vol.Schema(schema))

    async def async_step_zones_count(self, user_input=None):
        if user_input is not None:
            self.zones_count = user_input["zone_count"]
            return await self.async_step_zones()
        schema = {vol.Required("zone_count", default=8): vol.All(int, vol.Range(min=1, max=16))}
        return self.async_show_form(step_id="zones_count", data_schema=vol.Schema(schema))

    async def async_step_zones(self, user_input=None):
        if user_input is not None:
            self.zones_config = user_input
            return await self.async_step_connection()
        schema = {}
        for i in range(1, self.zones_count + 1):
            schema[vol.Optional(f"zone_{i}_name")] = str
            schema[vol.Optional(f"zone_{i}_type", default="motion")] = vol.In(ZONE_TYPES)
        return self.async_show_form(step_id="zones", data_schema=vol.Schema(schema))

    async def async_step_connection(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            await self.async_set_unique_id(f"{host}_{port}")
            self._abort_if_unique_id_configured()
            
            final_areas = {}
            for i in range(1, 3):
                name = self.areas_config.get(f"area_{i}_name")
                if name: final_areas[str(i)] = {"name": name, "code": self.areas_config.get(f"area_{i}_code", ""), "code_arm_required": True}
            
            final_outputs = {}
            if self.outputs_config.get("output_1_name"): final_outputs["1"] = {"name": self.outputs_config.get("output_1_name")}
            if self.outputs_config.get("output_2_name"): final_outputs["2"] = {"name": self.outputs_config.get("output_2_name")}
            
            final_zones = {}
            for i in range(1, self.zones_count + 1):
                name = self.zones_config.get(f"zone_{i}_name")
                if name: final_zones[str(i)] = {"name": name, "type": self.zones_config.get(f"zone_{i}_type", "motion")}
            
            data = {CONF_HOST: host, CONF_PORT: port, CONF_KEEP_ALIVE: user_input.get(CONF_KEEP_ALIVE, DEFAULT_KEEPALIVE), CONF_TIMEOUT: user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)}
            options = {CONF_AREAS: final_areas, CONF_ZONES: final_zones, CONF_OUTPUTS: final_outputs}
            return self.async_create_entry(title=host, data=data, options=options)

        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Optional(CONF_KEEP_ALIVE, default=DEFAULT_KEEPALIVE): int,
            vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
        })
        return self.async_show_form(step_id="connection", data_schema=data_schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CrowOptionsFlowHandler(config_entry)


class CrowOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.entry = config_entry
        self.areas_input = {}
        self.outputs_input = {}
    async def async_step_init(self, user_input=None): return await self.async_step_areas()
    async def async_step_areas(self, user_input=None):
        if user_input is not None:
            self.areas_input = user_input
            return await self.async_step_outputs()
        all_areas = self.entry.options.get(CONF_AREAS, {})
        schema = {}
        for i in range(1, 3):
            area = all_areas.get(str(i), {})
            schema[vol.Optional(f"area_{i}_name", description={"suggested_value": area.get("name", f"Area {i}")})] = str
            schema[vol.Optional(f"area_{i}_code", description={"suggested_value": area.get("code", "")})] = str
        return self.async_show_form(step_id="areas", data_schema=vol.Schema(schema))
    async def async_step_outputs(self, user_input=None):
        if user_input is not None:
            self.outputs_input = user_input
            return await self.async_step_zones()
        all_outputs = self.entry.options.get(CONF_OUTPUTS, {})
        schema = {}
        for i in range(1, 3):
            out = all_outputs.get(str(i), {})
            schema[vol.Optional(f"output_{i}_name", description={"suggested_value": out.get("name", "")})] = str
        return self.async_show_form(step_id="outputs", data_schema=vol.Schema(schema))
    async def async_step_zones(self, user_input=None):
        if user_input is not None:
            areas_config = {}
            for i in range(1, 3):
                 if self.areas_input.get(f"area_{i}_name"): areas_config[str(i)] = {"name": self.areas_input[f"area_{i}_name"], "code": self.areas_input.get(f"area_{i}_code",""), "code_arm_required": True}
            outputs_config = {}
            for i in range(1, 3):
                 if self.outputs_input.get(f"output_{i}_name"): outputs_config[str(i)] = {"name": self.outputs_input[f"output_{i}_name"]}
            zones_config = {}
            for k, v in user_input.items():
                if k.startswith("zone_") and k.endswith("_name") and v:
                    idx = k.split("_")[1]
                    zones_config[idx] = {"name": v, "type": user_input.get(f"zone_{idx}_type", "motion")}
            return self.async_create_entry(title="", data={CONF_AREAS: areas_config, CONF_ZONES: zones_config, CONF_OUTPUTS: outputs_config})
        all_zones = self.entry.options.get(CONF_ZONES, {})
        max_zone = max([int(k) for k in all_zones.keys()] or [8])
        schema = {}
        for i in range(1, max_zone + 1):
             z = all_zones.get(str(i), {})
             schema[vol.Optional(f"zone_{i}_name", description={"suggested_value": z.get("name", "")})] = str
             schema[vol.Optional(f"zone_{i}_type", default=z.get("type", "motion"))] = vol.In(ZONE_TYPES)
        return self.async_show_form(step_id="zones", data_schema=vol.Schema(schema))
