"""Diagnostics support for the Crow IP Module integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .binary_sensor import zone_unique_id
from .const import CONF_AREAS, CONF_ZONES, zone_device

TO_REDACT = {"code", "host"}


def _zone_registry_report(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Report where each zone's entity is registered and where it belongs.

    The device an entity is linked to is not shown anywhere in the UI; this makes
    a zone that ended up under another type's device (or with an entity id naming
    it) visible in one place.
    """
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    by_unique_id = {
        registry_entry.unique_id: registry_entry
        for registry_entry in er.async_entries_for_config_entry(entities, entry.entry_id)
    }

    report: dict[str, Any] = {}
    for zone_key, zone_info in (entry.options.get(CONF_ZONES) or {}).items():
        zone_type = zone_info.get("type")
        identifier, expected_name = zone_device(zone_type)
        row: dict[str, Any] = {
            "name": zone_info.get("name"),
            "type": zone_type,
            "expected_device": expected_name,
            "expected_device_identifier": identifier,
        }

        try:
            registry_entry = by_unique_id.get(zone_unique_id(int(zone_key)))
        except (TypeError, ValueError):
            registry_entry = None

        if registry_entry is not None:
            device = (
                devices.async_get(registry_entry.device_id)
                if registry_entry.device_id
                else None
            )
            row["entity_id"] = registry_entry.entity_id
            row["device_id"] = registry_entry.device_id
            row["device_name"] = device.name if device else None
            row["device_identifiers"] = (
                sorted(identifier for _, identifier in device.identifiers) if device else []
            )
            row["disabled_by"] = registry_entry.disabled_by

        report[str(zone_key)] = row

    return report


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    controller = getattr(entry.runtime_data, "controller", None)

    # Redact per-area codes from the options before exposing them.
    options = dict(entry.options)
    if CONF_AREAS in options:
        options[CONF_AREAS] = {
            area: async_redact_data(cfg, {"code"})
            for area, cfg in options[CONF_AREAS].items()
        }

    data: dict[str, Any] = {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": options,
    }

    try:
        data["zone_registry"] = _zone_registry_report(hass, entry)
    except Exception as err:  # noqa: BLE001 - diagnostics must never raise
        data["zone_registry"] = f"unavailable: {err}"

    if controller is not None:
        data["connected"] = controller.is_connected
        data["state"] = {
            "system": controller.system_state,
            "areas": controller.area_state,
            "zones": controller.zone_state,
            "outputs": controller.output_state,
        }

    return data
