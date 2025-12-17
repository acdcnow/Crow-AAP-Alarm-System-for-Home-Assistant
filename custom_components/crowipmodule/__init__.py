"""Crow/AAP IP Module init file."""
import asyncio
import logging

from pycrowipmodule import CrowIPAlarmPanel
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TIMEOUT, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN, DATA_CRW, CONF_KEEP_ALIVE,
    SIGNAL_ZONE_UPDATE, SIGNAL_AREA_UPDATE, 
    SIGNAL_SYSTEM_UPDATE, SIGNAL_OUTPUT_UPDATE
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.ALARM_CONTROL_PANEL, Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Crow IP Module from a config entry."""
    
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    keep_alive = entry.data.get(CONF_KEEP_ALIVE, 60)
    connection_timeout = entry.data.get(CONF_TIMEOUT, 10)
    
    # Init Controller
    # HINWEIS: hass.loop ist deprecated. Wir lassen es weg, moderne Libs nutzen get_running_loop()
    controller = CrowIPAlarmPanel(
        host, port, "0000", keep_alive, None, connection_timeout
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = controller

    # Callbacks
    def connection_fail_callback(data):
        _LOGGER.error("Could not establish a connection with the Crow Ip Module")

    def connected_callback(data):
        _LOGGER.info("Established a connection with the Crow Ip Module")

    def zones_updated_callback(data):
        async_dispatcher_send(hass, SIGNAL_ZONE_UPDATE, data)

    def areas_updated_callback(data):
        async_dispatcher_send(hass, SIGNAL_AREA_UPDATE, data)

    def system_updated_callback(data):
        async_dispatcher_send(hass, SIGNAL_SYSTEM_UPDATE, data)

    def output_updated_callback(data):
        async_dispatcher_send(hass, SIGNAL_OUTPUT_UPDATE, data)

    controller.callback_zone_state_change = zones_updated_callback
    controller.callback_area_state_change = areas_updated_callback
    controller.callback_system_state_change = system_updated_callback
    controller.callback_output_state_change = output_updated_callback
    controller.callback_connected = connected_callback
    controller.callback_login_timeout = connection_fail_callback

    _LOGGER.info("Starting CrowIpModule...")
    # Start non-blocking
    await hass.async_add_executor_job(controller.start)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Listen for shutdown
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda event: controller.stop())
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        controller = hass.data[DOMAIN][entry.entry_id]
        controller.stop()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
