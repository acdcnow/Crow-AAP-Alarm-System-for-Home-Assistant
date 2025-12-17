"""Config flow for Crow IP Module integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DEFAULT_KEEPALIVE,
    CONF_KEEP_ALIVE,
    CONF_AREAS,
    CONF_ZONES,
)

_LOGGER = logging.getLogger(__name__)

class CrowConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crow IP Module."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step (IP/Port)."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}_{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_HOST], data=user_input)

        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Optional(CONF_KEEP_ALIVE, default=DEFAULT_KEEPALIVE): int,
            vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): int,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CrowOptionsFlowHandler(config_entry)


class CrowOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.areas_input = {}

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_areas()

    async def async_step_areas(self, user_input=None):
        """Configure Areas."""
        if user_input is not None:
            self.areas_input = user_input
            return await self.async_step_zones()

        current_areas = self.config_entry.options.get(CONF_AREAS, {})
        schema = {}
        for i in range(1, 3):
            area_key = str(i)
            default_name = current_areas.get(area_key, {}).get("name", f"Area {i}")
            default_code = current_areas.get(area_key, {}).get("code", "")
            schema[vol.Optional(f"area_{i}_name", default=default_name)] = str
            schema[vol.Optional(f"area_{i}_code", default=default_code)] = str

        return self.async_show_form(step_id="areas", data_schema=vol.Schema(schema))

    async def async_step_zones(self, user_input=None):
        """Configure Zones."""
        if user_input is not None:
            # Process Areas
            areas_config = {}
            for i in range(1, 3):
                name = self.areas_input.get(f"area_{i}_name")
                code = self.areas_input.get(f"area_{i}_code")
                if name:
                    areas_config[str(i)] = {"name": name, "code": code, "code_arm_required": True}

            # Process Zones
            zones_config = {}
            for i in range(1, 17):
                name = user_input.get(f"zone_{i}_name")
                z_type = user_input.get(f"zone_{i}_type")
                if name:
                    zones_config[str(i)] = {"name": name, "type": z_type}

            return self.async_create_entry(
                title="",
                data={
                    CONF_AREAS: areas_config,
                    CONF_ZONES: zones_config
                }
            )

        current_zones = self.config_entry.options.get(CONF_ZONES, {})
        schema = {}
        for i in range(1, 17):
            zone_key = str(i)
            default_name = current_zones.get(zone_key, {}).get("name", "")
            default_type = current_zones.get(zone_key, {}).get("type", "motion")
            schema[vol.Optional(f"zone_{i}_name", description={"suggested_value": default_name})] = str
            schema[vol.Optional(f"zone_{i}_type", default=default_type)] = vol.In(["motion", "door", "window", "smoke", "safety"])

        return self.async_show_form(step_id="zones", data_schema=vol.Schema(schema))
