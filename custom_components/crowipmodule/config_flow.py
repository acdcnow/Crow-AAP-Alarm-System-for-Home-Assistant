"""Config flow for Crow IP Module integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DEFAULT_KEEPALIVE,
    CONF_KEEP_ALIVE,
    CONF_AREAS,
    CONF_ZONES,
    CONF_OUTPUTS,
)

_LOGGER = logging.getLogger(__name__)

ZONE_TYPES = [
    "motion", "door", "window", "smoke", "gas", "co", "tamper", "safety"
]

class CrowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crow IP Module."""

    VERSION = 1

    def __init__(self):
        self.areas_config = {}
        self.outputs_config = {}
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
            return await self.async_step_zones()

        schema = {
            vol.Optional("output_3_name", description={"suggested_value": "Modem"}): str,
            vol.Optional("output_4_name", description={"suggested_value": "Gateway"}): str,
        }
        return self.async_show_form(step_id="outputs", data_schema=vol.Schema(schema))

    async def async_step_zones(self, user_input=None):
        if user_input is not None:
            self.zones_config = user_input
            return await self.async_step_connection()

        schema = {}
        for i in range(1, 17):
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

            # --- Daten sicher zusammenbauen ---
            final_areas = {}
            for i in range(1, 3):
                name = self.areas_config.get(f"area_{i}_name")
                if name: 
                    final_areas[str(i)] = {
                        "name": name, 
                        "code": self.areas_config.get(f"area_{i}_code", ""), 
                        "code_arm_required": True
                    }

            final_outputs = {}
            if self.outputs_config.get("output_3_name"): 
                final_outputs["3"] = {"name": self.outputs_config.get("output_3_name")}
            if self.outputs_config.get("output_4_name"): 
                final_outputs["4"] = {"name": self.outputs_config.get("output_4_name")}

            final_zones = {}
            for i in range(1, 17):
                name = self.zones_config.get(f"zone_{i}_name")
                if name: 
                    final_zones[str(i)] = {
                        "name": name, 
                        "type": self.zones_config.get(f"zone_{i}_type", "motion")
                    }

            data = {
                CONF_HOST: host,
                CONF_PORT: port,
                CONF_KEEP_ALIVE: user_input.get(CONF_KEEP_ALIVE, DEFAULT_KEEPALIVE),
                CONF_TIMEOUT: user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            }
            options = {
                CONF_AREAS: final_areas,
                CONF_ZONES: final_zones,
                CONF_OUTPUTS: final_outputs
            }
            return self.async_create_entry(title=host, data=data, options=options)

        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Optional(CONF_KEEP_ALIVE, default=DEFAULT_KEEPALIVE): int,
            vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
        })
        return self.async_show_form(step_id="connection", data_schema=data_schema, errors=errors)

    async def async_step_import(self, import_data):
        return self.async_create_entry(title=import_data.get(CONF_HOST, "Crow Alarm"), data=import_data, options={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CrowOptionsFlowHandler(config_entry)


class CrowOptionsFlowHandler(config_entries.OptionsFlow):
    """Options Flow - FIX FÜR 500 ERROR."""

    def __init__(self, config_entry):
        self.config_entry = config_entry
        self.areas_input = {}
        self.outputs_input = {}

    async def async_step_init(self, user_input=None):
        return await self.async_step_areas()

    async def async_step_areas(self, user_input=None):
        if user_input is not None:
            self.areas_input = user_input
            return await self.async_step_outputs()
        
        # Sicherer Zugriff: Falls Optionen None sind, leeres Dict nehmen
        all_areas = self.config_entry.options.get(CONF_AREAS)
        if all_areas is None:
            all_areas = {}
            
        schema = {}
        for i in range(1, 3):
            # Prüfen ob der Eintrag für Bereich i existiert
            area_data = all_areas.get(str(i))
            if area_data is None:
                area_data = {}
            
            default_name = area_data.get("name", f"Area {i}")
            default_code = area_data.get("code", "")
            
            schema[vol.Optional(f"area_{i}_name", default=default_name)] = str
            schema[vol.Optional(f"area_{i}_code", default=default_code)] = str
            
        return self.async_show_form(step_id="areas", data_schema=vol.Schema(schema))

    async def async_step_outputs(self, user_input=None):
        if user_input is not None:
            self.outputs_input = user_input
            return await self.async_step_zones()

        all_outputs = self.config_entry.options.get(CONF_OUTPUTS)
        if all_outputs is None:
            all_outputs = {}
            
        out3 = all_outputs.get("3")
        if out3 is None: out3 = {}
        
        out4 = all_outputs.get("4")
        if out4 is None: out4 = {}

        schema = {
            vol.Optional("output_3_name", description={"suggested_value": out3.get("name", "")}): str,
            vol.Optional("output_4_name", description={"suggested_value": out4.get("name", "")}): str,
        }
        return self.async_show_form(step_id="outputs", data_schema=vol.Schema(schema))

    async def async_step_zones(self, user_input=None):
        if user_input is not None:
            # Speichern der Daten
            areas_config = {}
            for i in range(1, 3):
                name = self.areas_input.get(f"area_{i}_name")
                if name: 
                    areas_config[str(i)] = {
                        "name": name, 
                        "code": self.areas_input.get(f"area_{i}_code", ""), 
                        "code_arm_required": True
                    }
            
            outputs_config = {}
            if self.outputs_input.get("output_3_name"): 
                outputs_config["3"] = {"name": self.outputs_input.get("output_3_name")}
            if self.outputs_input.get("output_4_name"): 
                outputs_config["4"] = {"name": self.outputs_input.get("output_4_name")}

            zones_config = {}
            for i in range(1, 17):
                name = user_input.get(f"zone_{i}_name")
                if name: 
                    zones_config[str(i)] = {
                        "name": name, 
                        "type": user_input.get(f"zone_{i}_type", "motion")
                    }

            return self.async_create_entry(title="", data={
                CONF_AREAS: areas_config, 
                CONF_ZONES: zones_config, 
                CONF_OUTPUTS: outputs_config
            })

        all_zones = self.config_entry.options.get(CONF_ZONES)
        if all_zones is None:
            all_zones = {}
            
        schema = {}
        for i in range(1, 17):
            zone_data = all_zones.get(str(i))
            if zone_data is None:
                zone_data = {}
            
            default_name = zone_data.get("name", "")
            raw_type = zone_data.get("type", "motion")
            
            # WICHTIGE Valdierung: Wenn der Typ in der YAML falsch war,
            # stürzt das Dropdown ab. Wir fangen das ab.
            if raw_type not in ZONE_TYPES:
                raw_type = "motion"
                
            schema[vol.Optional(f"zone_{i}_name", description={"suggested_value": default_name})] = str
            schema[vol.Optional(f"zone_{i}_type", default=raw_type)] = vol.In(ZONE_TYPES)
            
        return self.async_show_form(step_id="zones", data_schema=vol.Schema(schema))
