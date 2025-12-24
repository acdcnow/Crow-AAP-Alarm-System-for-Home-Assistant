"""Crow/AAP IP Module init file."""
import asyncio
import logging
import voluptuous as vol

from .crow_service import CrowIPAlarmPanel
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import (
    CONF_HOST, CONF_PORT, CONF_TIMEOUT, EVENT_HOMEASSISTANT_STOP, Platform
)
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN, SIGNAL_ZONE_UPDATE, SIGNAL_AREA_UPDATE, 
    SIGNAL_SYSTEM_UPDATE, SIGNAL_OUTPUT_UPDATE, CONF_KEEP_ALIVE
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({}, extra=vol.ALLOW_EXTRA)}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    keep_alive = entry.data.get(CONF_KEEP_ALIVE, 60)
    connection_timeout = entry.data.get(CONF_TIMEOUT, 10)
    
    code = ""
    # Wir laden keinen Default-Code mehr aktiv vor, da der User ihn eingeben muss.
    # Aber wir übergeben ihn falls vorhanden als Fallback.
    if entry.options and "areas" in entry.options:
         area1 = entry.options["areas"].get("1", {})
         code = area1.get("code", "")

    controller = CrowIPAlarmPanel(
        host, port, code, keep_alive, hass.loop, connection_timeout
    )

    hass.data[DOMAIN][entry.entry_id] = controller

    def _thread_safe_send(signal, data):
        hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, signal, data)

    controller.callback_zone_state_change = lambda data: _thread_safe_send(SIGNAL_ZONE_UPDATE, data)
    controller.callback_area_state_change = lambda data: _thread_safe_send(SIGNAL_AREA_UPDATE, data)
    controller.callback_system_state_change = lambda data: _thread_safe_send(SIGNAL_SYSTEM_UPDATE, data)
    controller.callback_output_state_change = lambda data: _thread_safe_send(SIGNAL_OUTPUT_UPDATE, data)
    controller.callback_connected = lambda data: _LOGGER.info("Connected to Crow IP Module")
    controller.callback_login_timeout = lambda data: _LOGGER.error("Connection failed")

    _LOGGER.info("Starting CrowIpModule connection...")
    controller.start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda event: controller.stop())
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        controller = hass.data[DOMAIN][entry.entry_id]
        controller.stop()
        # Warte auf Socket Release
        await asyncio.sleep(1) 
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
