"""Config flow for Crow IP Module integration."""
import logging
import re
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
    ZONE_TYPES,
)

_LOGGER = logging.getLogger(__name__)

# Zone type strings are declared in const.py (ZONE_TYPES); the flow only picks the
# type, which decides the icon of the sensor - not which device it lives on.
DEFAULT_ZONE_TYPE = "window"

# Translation key of the zone type dropdown: the option labels live in
# ``selector.zone_type.options`` in strings.json / translations.
ZONE_TYPE_SELECTOR = "zone_type"

# A zone field is named ``zone_<index>_<field>``. The index is parsed out of the
# field name, so a submitted value can only ever be stored on the zone it was
# entered for - never on the zone that happens to sit at the same position of a
# form page.
_ZONE_FIELD = re.compile(r"^zone_(\d+)_(name|type)$")


def _zone_type_selector() -> selector.SelectSelector:
    """Dropdown for the type of one zone.

    The stored value stays the plain type string from ``ZONE_TYPES`` (that is
    what the zone devices and device classes are keyed by), but the dropdown
    shows a translated label instead of the raw value.
    """
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=ZONE_TYPES,
            translation_key=ZONE_TYPE_SELECTOR,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def zone_schema(count: int, zones: dict) -> vol.Schema:
    """Build the zone form: one name/type pair per zone, in zone order.

    All zones are configured in a single step. Earlier releases spread them over
    pages of four and tracked the current page in the flow handler, which made
    the page depend on hidden state rather than on the form the user submitted.
    """
    schema = {}
    for i in range(1, count + 1):
        zone = zones.get(str(i), {})
        schema[
            vol.Optional(
                f"zone_{i}_name",
                description={"suggested_value": zone.get("name", "")},
            )
        ] = str
        schema[
            vol.Optional(
                f"zone_{i}_type",
                default=zone.get("type", DEFAULT_ZONE_TYPE),
            )
        ] = _zone_type_selector()
    return vol.Schema(schema)


def merge_zones(target: dict, user_input) -> None:
    """Store a submitted zone form into ``target``, keyed by the zone index.

    Every field is re-derived from its own name, so the mapping between a zone
    and its type cannot shift - not when the zone count changes, not when the
    form is re-submitted, and not when a zone was left untouched (its stored
    value then simply stays in place).
    """
    for key, value in (user_input or {}).items():
        if (match := _ZONE_FIELD.match(key)) is None:
            continue
        index, field = match.groups()
        target.setdefault(str(index), {})[field] = value


def existing_zones(entry) -> dict:
    """Return the stored zone map of a config entry, as plain dicts."""
    return {str(k): dict(v) for k, v in (entry.options.get(CONF_ZONES) or {}).items()}


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
            return await self.async_step_zones()

        if user_input is not None:
            outputs_config = {}
            for i in range(1, count + 1):
                name = user_input.get(f"output_{i}_name")
                if name:
                    outputs_config[str(i)] = {"name": name}
            
            self._options[CONF_OUTPUTS] = outputs_config
            return await self.async_step_zones()

        schema = {}
        for i in range(1, count + 1):
            default_name = f"Output {i}"
            schema[vol.Optional(f"output_{i}_name", description={"suggested_value": default_name})] = str

        return self.async_show_form(step_id="outputs", data_schema=vol.Schema(schema))

    async def async_step_zones(self, user_input=None):
        """Step 4: name and type of every zone, as one list of zone pairs."""
        count = self._data.get(CONF_NUM_ZONES, DEFAULT_NUM_ZONES)

        if user_input is not None:
            merge_zones(self._options[CONF_ZONES], user_input)
            return self.async_create_entry(
                title=self._data[CONF_HOST],
                data=self._data,
                options=self._options,
            )

        return self.async_show_form(
            step_id="zones",
            data_schema=zone_schema(count, self._options[CONF_ZONES]),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return CrowOptionsFlowHandler()


class CrowOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self):
        self._temp_data = {}
        self._temp_options = {}

    def _zone_source(self) -> dict:
        """Stored zones overlaid with what this flow already collected.

        A zone that is not part of the submitted form keeps the value it has now
        instead of being dropped.
        """
        merged = existing_zones(self.config_entry)
        for index, fields in (self._temp_options.get(CONF_ZONES) or {}).items():
            merged.setdefault(str(index), {}).update(fields)
        return merged

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
            return await self.async_step_zones()

        if user_input is not None:
            self._temp_options[CONF_OUTPUTS] = {}
            for i in range(1, count + 1):
                name = user_input.get(f"output_{i}_name")
                if name:
                    self._temp_options[CONF_OUTPUTS][str(i)] = {"name": name}
            
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
        """Name and type of every zone, in one list of zone pairs."""
        count = self._temp_data.get(CONF_NUM_ZONES, DEFAULT_NUM_ZONES)

        if user_input is not None:
            merged = self._zone_source()
            merge_zones(merged, user_input)
            # Zones the user did not touch stay exactly as they are.
            self._temp_options[CONF_ZONES] = merged

            new_data = self.config_entry.data.copy()
            new_data.update(self._temp_data)
            # Only update entry.data here; options are saved by async_create_entry below.
            # Passing options= here AND data={} to async_create_entry would wipe the options.
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            # async_create_entry saves self._temp_options as the new options and
            # automatically triggers update_listener → reload. No manual reload needed.
            return self.async_create_entry(title="", data=self._temp_options)

        return self.async_show_form(
            step_id="zones",
            data_schema=zone_schema(count, self._zone_source()),
        )
