"""Drive the Crow IP Module config + options flow and check translation coverage.

Runs without Home Assistant: only ``voluptuous`` (and a handful of HA stubs) are
needed. This exercises the real flow code paths and asserts that

* every schema field the flow renders has a label in ``strings.json``, and
* the data/options shape a finished flow produces matches what the entity
  platforms expect.

Run:  python -m pip install --target tests/vendor voluptuous
      python tests/verify_config_flow.py
"""

from __future__ import annotations

import asyncio
import enum
import json
import os
import pathlib
import sys
import types

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# voluptuous is the only third-party dependency of the config flow. Look for it
# in the interpreter, then next to this script (e.g. `pip install --target`).
for candidate in (
    pathlib.Path(os.environ.get("CROW_VERIFY_LIBS", "")),
    pathlib.Path(__file__).resolve().parent / "vendor",
):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))

try:
    import voluptuous as vol  # noqa: E402
except ModuleNotFoundError:  # pragma: no cover - dependency hint
    raise SystemExit(
        "voluptuous is required: python -m pip install --target tests/vendor voluptuous"
    ) from None

FAILURES: list[str] = []


def check(label: str, condition: bool, extra: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {label}{(' -> ' + extra) if extra and not condition else ''}")
    if not condition:
        FAILURES.append(label)


def _rejects(validator, value) -> bool:
    try:
        validator(value)
    except vol.Invalid:
        return True
    return False


def mod(name: str) -> types.ModuleType:
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


ha = mod("homeassistant")
ha_const = mod("homeassistant.const")
ha_core = mod("homeassistant.core")
ha_ce = mod("homeassistant.config_entries")
ha.config_entries = ha_ce

ha_const.CONF_HOST = "host"
ha_const.CONF_PORT = "port"
ha_const.CONF_TIMEOUT = "timeout"
ha_core.callback = lambda func: func


class FlowResultType(enum.StrEnum):
    FORM = "form"
    CREATE_ENTRY = "create_entry"
    ABORT = "abort"


class FlowHandler:
    """Small subset of data_entry_flow.FlowHandler."""

    def __init__(self) -> None:
        self.hass = types.SimpleNamespace(
            async_add_executor_job=lambda func, *args: asyncio.sleep(0, result=func(*args))
        )
        self._unique_id: str | None = None

    async def async_set_unique_id(self, unique_id: str) -> None:
        self._unique_id = unique_id

    def _abort_if_unique_id_configured(self) -> None:
        return None


class ConfigFlow(FlowHandler):
    """Minimal ConfigFlow: records forms and entries instead of the UI."""

    def __init_subclass__(cls, *, domain: str | None = None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.domain = domain

    def __init__(self) -> None:
        super().__init__()
        self.forms: dict[str, vol.Schema] = {}

    def async_show_form(self, *, step_id, data_schema, errors=None, **kwargs):
        # CrowConfigFlow overrides __init__ without calling super(), exactly like
        # the real integration does, so lazily create the recorder.
        self.forms = getattr(self, "forms", {})
        self.forms[step_id] = data_schema
        return {
            "type": FlowResultType.FORM,
            "step_id": step_id,
            "data_schema": data_schema,
            "errors": errors or {},
        }

    def async_create_entry(self, *, title, data, options=None):
        return {
            "type": FlowResultType.CREATE_ENTRY,
            "title": title,
            "data": data,
            "options": options,
        }


class OptionsFlow(FlowHandler):
    def __init__(self) -> None:
        super().__init__()
        self.forms: dict[str, vol.Schema] = {}
        self.config_entry = None

    def async_show_form(self, *, step_id, data_schema, errors=None, **kwargs):
        self.forms = getattr(self, "forms", {})
        self.forms[step_id] = data_schema
        return {
            "type": FlowResultType.FORM,
            "step_id": step_id,
            "data_schema": data_schema,
        }

    def async_create_entry(self, *, title=None, data):
        return {"type": FlowResultType.CREATE_ENTRY, "title": title, "data": data}


ha_ce.ConfigFlow = ConfigFlow
ha_ce.OptionsFlow = OptionsFlow
ha_ce.FlowResultType = FlowResultType


class ConfigEntry:
    """Marker type; the package __init__ only imports it for annotations."""


class Platform(enum.StrEnum):
    ALARM_CONTROL_PANEL = "alarm_control_panel"
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    SENSOR = "sensor"
    SWITCH = "switch"


class EntityCategory(enum.StrEnum):
    DIAGNOSTIC = "diagnostic"


ha_ce.ConfigEntry = ConfigEntry
ha_const.Platform = Platform
ha_const.EntityCategory = EntityCategory
ha_const.EVENT_HOMEASSISTANT_STOP = "homeassistant_stop"
ha_core.Event = type("Event", (), {})
ha_core.HomeAssistant = type("HomeAssistant", (), {})


# The package __init__ pulls in the helper submodules, so they must resolve
# even though this script only drives the config flow.
ha_helpers = mod("homeassistant.helpers")
ha_helpers.__path__ = []
ha.helpers = ha_helpers


# Minimal stand-in for homeassistant.helpers.selector. It records the config so
# the harness can assert the translation key and the offered options, and it
# validates like the real selector so a bad payload is rejected here too.
class SelectSelectorConfig:
    def __init__(self, *, options, translation_key=None, **kwargs):
        self.options = list(options)
        self.translation_key = translation_key
        self.extra = kwargs


class SelectSelector:
    def __init__(self, config):
        self.config = config

    def __call__(self, value):
        if value not in self.config.options:
            raise vol.Invalid(f"{value!r} is not a valid option")
        return value


sel = mod("homeassistant.helpers.selector")
sel.SelectSelector = SelectSelector
sel.SelectSelectorConfig = SelectSelectorConfig
ha_helpers.selector = sel

dr = mod("homeassistant.helpers.device_registry")
dr.DeviceInfo = dict
dr.async_get = lambda hass: None
disp = mod("homeassistant.helpers.dispatcher")
disp.async_dispatcher_connect = lambda *args, **kwargs: (lambda: None)
disp.async_dispatcher_send = lambda *args, **kwargs: None
ep = mod("homeassistant.helpers.entity_platform")
ep.AddConfigEntryEntitiesCallback = object
ent = mod("homeassistant.helpers.entity")
ent.Entity = type("Entity", (), {})
comp = mod("homeassistant.components")
comp.__path__ = []
ha.components = comp

INTEGRATION = REPO / "custom_components"
sys.path.insert(0, str(INTEGRATION.parent))
from custom_components.crowipmodule import config_flow as cf  # noqa: E402

STRINGS = json.loads((INTEGRATION / "crowipmodule" / "strings.json").read_text(encoding="utf-8"))


def schema_keys(schema: vol.Schema) -> list[str]:
    return [str(getattr(key, "schema", key)) for key in schema.schema]


def translation_keys(section: str, step: str) -> set[str]:
    return set(STRINGS.get(section, {}).get("step", {}).get(step, {}).get("data", {}).keys())


def validator_for(schema: vol.Schema, key: str):
    """Return the validator declared for ``key`` in a schema, or None."""
    for marker, value in schema.schema.items():
        if str(getattr(marker, "schema", marker)) == key:
            return value
    return None


async def drive_config_flow() -> dict:
    flow = cf.CrowConfigFlow()
    flow.hass = types.SimpleNamespace(
        async_add_executor_job=lambda func, *args: asyncio.sleep(0, result=True)
    )

    # Patch the TCP probe so the flow can be driven offline.
    cf._test_connection = lambda host, port, timeout: True

    result = await flow.async_step_user()
    check("user step renders", result["type"] is FlowResultType.FORM)
    user_keys = schema_keys(result["data_schema"])
    check(
        "user step has all connection keys",
        {"host", "port", "keepalive_interval", "timeout", "firmware_version",
         "number_of_areas", "number_of_zones", "number_of_outputs",
         "arm_sequence"} <= set(user_keys),
        str(user_keys),
    )
    check(
        "user step labels are translated",
        set(user_keys) <= translation_keys("config", "user"),
        str(set(user_keys) - translation_keys("config", "user")),
    )

    arm_selector = validator_for(result["data_schema"], "arm_sequence")
    check(
        "arm_sequence renders as a select selector",
        isinstance(arm_selector, SelectSelector),
        type(arm_selector).__name__,
    )
    check(
        "arm_sequence selector offers every supported mode",
        sorted(arm_selector.config.options) == sorted(cf.ARM_SEQUENCES),
        str(arm_selector.config.options),
    )
    check(
        "arm_sequence selector uses a translation key",
        arm_selector.config.translation_key == "arm_sequence",
        str(arm_selector.config.translation_key),
    )
    check(
        "arm_sequence rejects an unknown mode",
        _rejects(arm_selector, "not_a_mode"),
    )
    check(
        "arm_sequence accepts both documented modes",
        all(arm_selector(mode) == mode for mode in cf.ARM_SEQUENCES),
    )

    payload = {
        "host": "192.168.1.50",
        "port": 5002,
        "keepalive_interval": 300,
        "timeout": 10,
        "firmware_version": "Ver 2.10.3628 2017",
        "arm_sequence": "command_then_keypad",
        "number_of_areas": 2,
        "number_of_outputs": 2,
        "number_of_zones": 5,
    }
    result = await flow.async_step_user(payload)
    check("areas step follows the user step", result["step_id"] == "areas", result["step_id"])
    area_keys = schema_keys(result["data_schema"])
    check("areas step labels translated", set(area_keys) <= translation_keys("config", "areas"),
          str(set(area_keys) - translation_keys("config", "areas")))

    result = await flow.async_step_areas({"area_1_name": "House", "area_1_code": "1234",
                                          "area_2_name": "Garage", "area_2_code": ""})
    check("outputs step follows areas", result["step_id"] == "outputs", result["step_id"])
    output_keys = schema_keys(result["data_schema"])
    check("outputs step labels translated", set(output_keys) <= translation_keys("config", "outputs"),
          str(set(output_keys) - translation_keys("config", "outputs")))

    result = await flow.async_step_outputs({"output_1_name": "Gate", "output_2_name": "Siren"})
    check("zones step follows outputs", result["step_id"] == "zones", result["step_id"])

    # 5 zones at PAGE_SIZE=4 -> two pages.
    page_keys: set[str] = set()
    result = await flow.async_step_zones({"zone_1_name": "Front Door", "zone_1_type": "door",
                                         "zone_2_name": "Kitchen", "zone_2_type": "motion",
                                         "zone_3_name": "Window", "zone_3_type": "window",
                                         "zone_4_name": "Smoke", "zone_4_type": "smoke"})
    check("zones step paginates", result["step_id"] == "zones", result["step_id"])
    page_keys |= set(schema_keys(result["data_schema"]))

    result = await flow.async_step_zones({"zone_5_name": "Office", "zone_5_type": "motion"})
    check("flow finishes after the last page", result["type"] is FlowResultType.CREATE_ENTRY,
          str(result["type"]))

    all_zone_labels = translation_keys("config", "zones")
    check(
        "every rendered zone field has a label",
        page_keys <= all_zone_labels,
        str(page_keys - all_zone_labels),
    )
    check("zone types cover all supported classes",
          set(cf.ZONE_TYPES) == {"window", "motion", "door", "smoke", "gas", "co", "tamper", "safety"},
          str(cf.ZONE_TYPES))
    check("firmware_date derived from profile",
          result["data"]["firmware_date"] == cf.FIRMWARE_PROFILES["Ver 2.10.3628 2017"],
          result["data"].get("firmware_date"))
    return result


async def drive_options_flow(created: dict) -> None:
    class FakeEntry:
        pass

    entry = FakeEntry()
    entry.entry_id = "entry-1"
    entry.title = "192.168.1.50"
    entry.data = created["data"]
    entry.options = created["options"]

    flow = cf.CrowConfigFlow.async_get_options_flow(entry)
    check("options flow is an OptionsFlow", isinstance(flow, cf.CrowOptionsFlowHandler))

    flow.hass = types.SimpleNamespace(
        async_add_executor_job=lambda func, *args: asyncio.sleep(0, result=True)
    )
    flow.config_entry = entry

    result = await flow.async_step_init()
    check("options init step renders", result["step_id"] == "init")
    init_keys = set(schema_keys(result["data_schema"]))
    check("options init labels translated", init_keys <= translation_keys("options", "init"),
          str(init_keys - translation_keys("options", "init")))

    result = await flow.async_step_init(dict(entry.data))
    check("options areas step follows init", result["step_id"] == "areas", result["step_id"])
    check("options areas labels translated",
          set(schema_keys(result["data_schema"])) <= translation_keys("options", "areas"))

    result = await flow.async_step_areas({"area_1_name": "House", "area_1_code": "1234",
                                          "area_2_name": "Garage", "area_2_code": ""})
    check("options outputs step follows areas", result["step_id"] == "outputs", result["step_id"])
    result = await flow.async_step_outputs({"output_1_name": "Gate", "output_2_name": "Siren"})
    check("options zones step follows outputs", result["step_id"] == "zones", result["step_id"])


async def main() -> None:
    created = await drive_config_flow()
    print("\n== Created entry shape ==")
    check("title is the host", created["title"] == "192.168.1.50")
    check("area options stored", created["options"]["areas"]["1"]["name"] == "House")
    check("output options stored", created["options"]["outputs"]["2"]["name"] == "Siren")
    check("zone options stored", created["options"]["zones"]["4"]["type"] == "smoke")
    check("arm sequence stored in entry.data",
          created["data"].get("arm_sequence") == "command_then_keypad",
          str(created["data"].get("arm_sequence")))
    check("default arm sequence is command then keypad",
          cf.DEFAULT_ARM_SEQUENCE == "command_then_keypad",
          str(cf.DEFAULT_ARM_SEQUENCE))

    print("\n== Options flow ==")
    await drive_options_flow(created)

    print("\n== Translation file parity ==")
    en = json.loads((INTEGRATION / "crowipmodule" / "translations" / "en.json").read_text(encoding="utf-8"))
    check("translations/en.json matches strings.json", en == STRINGS)

    option_labels = STRINGS.get("selector", {}).get("arm_sequence", {}).get("options", {})
    check(
        "strings.json labels every arm sequence option",
        set(option_labels) == set(cf.ARM_SEQUENCES) and all(option_labels.values()),
        str(option_labels),
    )

    for lang in ("de", "es", "fr", "it"):
        data = json.loads(
            (INTEGRATION / "crowipmodule" / "translations" / f"{lang}.json").read_text(encoding="utf-8")
        )
        missing = {
            f"{section}.step.{step}"
            for section in ("config", "options")
            for step in STRINGS.get(section, {}).get("step", {})
            if step not in data.get(section, {}).get("step", {})
        }
        check(f"{lang}.json covers every step", not missing, str(missing))

        lang_options = data.get("selector", {}).get("arm_sequence", {}).get("options", {})
        check(
            f"{lang}.json translates every arm sequence option",
            set(lang_options) == set(cf.ARM_SEQUENCES) and all(lang_options.values()),
            str(lang_options),
        )
        check(
            f"{lang}.json labels the arm_sequence field in both steps",
            "arm_sequence" in data.get("config", {}).get("step", {}).get("user", {}).get("data", {})
            and "arm_sequence" in data.get("options", {}).get("step", {}).get("init", {}).get("data", {}),
        )


if __name__ == "__main__":
    asyncio.run(main())
    print("\n" + "=" * 40)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for item in FAILURES:
            print(f"  - {item}")
        sys.exit(1)
    print("ALL CHECKS PASSED")
