"""Crow/AAP IP Module init file."""
import asyncio
import logging
import voluptuous as vol

from pycrowipmodule import CrowIPAlarmPanel
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import (
    CONF_HOST, CONF_PORT, CONF_TIMEOUT, EVENT_HOMEASSISTANT_STOP, Platform
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, DATA_CRW, CONF_KEEP_ALIVE,
    CONF_AREAS, CONF_ZONES, CONF_OUTPUTS,
    DEFAULT_PORT, DEFAULT_KEEPALIVE, DEFAULT_TIMEOUT,
    SIGNAL_ZONE_UPDATE, SIGNAL_AREA_UPDATE, 
    SIGNAL_SYSTEM_UPDATE, SIGNAL_OUTPUT_UPDATE
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

# Import Schema
CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({}, extra=vol.ALLOW_EXTRA)}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Crow IP Module component from YAML (Import)."""
    hass.data.setdefault(DOMAIN, {})
    if DOMAIN in config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=config[DOMAIN]
            )
        )
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Crow IP Module from a config entry."""
    
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    keep_alive = entry.data.get(CONF_KEEP_ALIVE, 60)
    connection_timeout = entry.data.get(CONF_TIMEOUT, 10)
    
    # 1. Controller Init
    # Wir übergeben keinen Loop, da pycrowipmodule (hoffentlich) den laufenden Loop nutzt oder Threads verwendet.
    controller = CrowIPAlarmPanel(
        host, port, "0000", keep_alive, None, connection_timeout
    )

    hass.data[DOMAIN][entry.entry_id] = controller

    # 2. Thread-Safe Callbacks
    # WICHTIG: Da die Crow-Lib in einem eigenen Thread läuft, müssen wir
    # updates Thread-Safe an den HA-Main-Loop übergeben.
    
    def _thread_safe_send(signal, data):
        """Helper to send dispatcher signals thread-safely."""
        hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, signal, data)

    def zones_updated_callback(data):
        _thread_safe_send(SIGNAL_ZONE_UPDATE, data)

    def areas_updated_callback(data):
        _thread_safe_send(SIGNAL_AREA_UPDATE, data)

    def system_updated_callback(data):
        _thread_safe_send(SIGNAL_SYSTEM_UPDATE, data)

    def output_updated_callback(data):
        _thread_safe_send(SIGNAL_OUTPUT_UPDATE, data)

    def connected_callback(data):
        _LOGGER.info("Established a connection with the Crow Ip Module")

    def connection_fail_callback(data):
        _LOGGER.error("Could not establish a connection with the Crow Ip Module")

    # Callbacks registrieren
    controller.callback_zone_state_change = zones_updated_callback
    controller.callback_area_state_change = areas_updated_callback
    controller.callback_system_state_change = system_updated_callback
    controller.callback_output_state_change = output_updated_callback
    controller.callback_connected = connected_callback
    controller.callback_login_timeout = connection_fail_callback

    _LOGGER.info("Starting CrowIpModule background task...")
    
    # 3. Starten OHNE Blockieren (Fix für Timeout Fehler)
    # Wir rufen .start() im Executor auf, warten aber NICHT darauf (kein await).
    # Damit kann async_setup_entry sofort 'True' zurückgeben und HA bootet weiter,
    # während der Controller im Hintergrund versucht sich zu verbinden.
    hass.async_add_executor_job(controller.start)

    # 4. Plattformen laden
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # 5. Shutdown Listener
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda event: controller.stop())
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        controller = hass.data[DOMAIN][entry.entry_id]
        # Stop auch im Executor ausführen, um Blocking zu vermeiden
        await hass.async_add_executor_job(controller.stop)
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
