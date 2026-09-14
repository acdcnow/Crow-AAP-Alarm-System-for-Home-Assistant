"""Crow/AAP IP Module init file."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_HOST, CONF_PORT, CONF_TIMEOUT, EVENT_HOMEASSISTANT_STOP, Platform
)
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .pycrowipmodule import CrowIPAlarmPanel

from .const import (
    DOMAIN, CONF_KEEP_ALIVE, DEFAULT_KEEPALIVE,
    SIGNAL_ZONE_UPDATE, SIGNAL_AREA_UPDATE,
    SIGNAL_SYSTEM_UPDATE, SIGNAL_OUTPUT_UPDATE, SIGNAL_CONNECTION_UPDATE
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Crow IP Module component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Crow IP Module from a config entry."""
    _LOGGER.info("Starting Crow IP Module setup for entry: %s", entry.title)
    
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    keep_alive = entry.data.get(CONF_KEEP_ALIVE, DEFAULT_KEEPALIVE)
    connection_timeout = entry.data.get(CONF_TIMEOUT, 10)
    
    try:
        controller = CrowIPAlarmPanel(
            host, port, "0000", keep_alive, None, connection_timeout
        )
    except Exception as e:
        _LOGGER.error("Failed to initialize CrowIPAlarmPanel object: %s", e)
        return False

    hass.data[DOMAIN][entry.entry_id] = controller

    # ... (HIER FOLGEN DIE GANZEN CALLBACKS WIE ZUVOR) ...
    # (Ich kürze das hier ab, kopiere deine Callbacks 1:1 wieder rein)
    def _thread_safe_send(signal, data):
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
        """Called by the client on connect (True) and disconnect (False)."""
        connected = bool(data)
        _thread_safe_send(SIGNAL_CONNECTION_UPDATE, connected)
        if not connected:
            _LOGGER.warning("Connection lost to Crow IP Module.")
            return

        _LOGGER.info("Successfully connected to Crow IP Module at %s", host)

        async def delayed_refresh():
            await asyncio.sleep(2.0)
            async_dispatcher_send(hass, SIGNAL_SYSTEM_UPDATE, None)
            async_dispatcher_send(hass, SIGNAL_AREA_UPDATE, None)
            async_dispatcher_send(hass, SIGNAL_ZONE_UPDATE, None)
            async_dispatcher_send(hass, SIGNAL_OUTPUT_UPDATE, None)
        # create_task is NOT thread-safe — use run_coroutine_threadsafe to
        # schedule the coroutine onto HA's event loop from the panel's background thread.
        asyncio.run_coroutine_threadsafe(delayed_refresh(), hass.loop)

    def connection_fail_callback(data):
        _LOGGER.warning("Connection lost/failed to Crow IP Module. Reconnecting...")
        _thread_safe_send(SIGNAL_CONNECTION_UPDATE, False)

    controller.callback_zone_state_change = zones_updated_callback
    controller.callback_area_state_change = areas_updated_callback
    controller.callback_system_state_change = system_updated_callback
    controller.callback_output_state_change = output_updated_callback
    controller.callback_connected = connected_callback
    controller.callback_login_timeout = connection_fail_callback

    _LOGGER.debug("Waiting 2s for socket cleanup before start...")
    await asyncio.sleep(2.0)

    _LOGGER.info("Starting CrowIpModule background thread...")
    try:
        hass.async_add_executor_job(controller.start)
    except Exception as e:
         _LOGGER.error("Fatal error starting controller thread: %s", e)
         return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda event: controller.stop())
    )

    # --- NewNEU: Listener for Option-cahnge regestration ---
    entry.async_on_unload(entry.add_update_listener(update_listener))
    # --------------------------------------------------------

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info("Unloading Crow IP Module entry: %s", entry.title)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        controller = hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("Stopping Crow IP Module connection and releasing socket...")
        try:
            await hass.async_add_executor_job(controller.stop)
        except Exception as e:
            _LOGGER.error("Error stopping controller during unload: %s", e)

    # Allow the OS and Crow IP module to cleanly release the single TCP socket
    _LOGGER.debug("Waiting 2s for TCP socket release...")
    await asyncio.sleep(2.0)
    return unload_ok

# --- new: This function is reloading the integartion if something has changed in the options order to take the changes into account! ---
async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener to reload the integration when options are changed."""
    _LOGGER.info("Options updated, reloading Crow IP Module integration...")
    await hass.config_entries.async_reload(entry.entry_id)
