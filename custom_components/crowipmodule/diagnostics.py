"""Diagnostics support for the Crow IP Module integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_AREAS

TO_REDACT = {"code", "host"}


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

    if controller is not None:
        data["connected"] = controller.is_connected
        data["state"] = {
            "system": controller.system_state,
            "areas": controller.area_state,
            "zones": controller.zone_state,
            "outputs": controller.output_state,
        }

    return data
