"""Crow/AAP IP Module init file."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_TIMEOUT,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_FW_DATE,
    CONF_FW_VERSION,
    CONF_KEEP_ALIVE,
    DEFAULT_FW_DATE,
    DEFAULT_FW_VERSION,
    DEFAULT_KEEPALIVE,
    DEFAULT_TIMEOUT,
    DEVICE_NAME,
    IDENTIFIER_HUB,
    MODEL_IP_MODULE,
    SIGNAL_AREA_UPDATE,
    SIGNAL_CONNECTION_UPDATE,
    SIGNAL_OUTPUT_UPDATE,
    SIGNAL_SYSTEM_UPDATE,
    SIGNAL_ZONE_UPDATE,
)
from .device import CrowRuntimeData, build_device_info
from .pycrowipmodule import CrowIPAlarmPanel

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
    # All state lives on the config entry (``entry.runtime_data``) instead of
    # ``hass.data``. The hook is kept so a YAML block is still accepted and can
    # be picked up by the config flow's import step.
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Crow IP Module from a config entry."""
    _LOGGER.info("Starting Crow IP Module setup for entry: %s", entry.title)
    
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    keep_alive = entry.data.get(CONF_KEEP_ALIVE, DEFAULT_KEEPALIVE)
    connection_timeout = entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)

    try:
        controller = CrowIPAlarmPanel(
            host, port, "0000", keep_alive, None, connection_timeout
        )
    except Exception as err:  # noqa: BLE001 - surface any constructor problem
        _LOGGER.error("Failed to initialize CrowIPAlarmPanel object: %s", err)
        return False

    fw_version = entry.data.get(CONF_FW_VERSION, DEFAULT_FW_VERSION)
    fw_date = entry.data.get(CONF_FW_DATE, DEFAULT_FW_DATE)
    entry.runtime_data = CrowRuntimeData(
        controller=controller, firmware=f"{fw_version} ({fw_date})"
    )

    # The panel client runs in its own thread, so every callback has to hop back
    # onto the event loop before it may touch Home Assistant state.
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

    # Register the main panel before the platforms are set up. The zone
    # sub-devices link to it through ``via_device_id``, which needs a device id,
    # so the parent has to exist first.
    device_registry = dr.async_get(hass)
    hub_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **build_device_info(
            name=DEVICE_NAME,
            host=host,
            identifier=IDENTIFIER_HUB,
            model=MODEL_IP_MODULE,
            sw_version=entry.runtime_data.firmware,
        ),
    )
    entry.runtime_data.device_id = hub_device.id

    # Give the panel a moment to release a socket left over from a reload.
    _LOGGER.debug("Waiting 2s for socket cleanup before start...")
    await asyncio.sleep(2.0)

    _LOGGER.info("Starting CrowIpModule background thread...")
    await hass.async_add_executor_job(controller.start)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_stop(_event: Event) -> None:
        """Close the panel connection when Home Assistant stops."""
        await hass.async_add_executor_job(controller.stop)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    # Reload the entry so option changes (names, codes, zone types) take effect.
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Crow IP Module entry: %s", entry.title)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if (runtime_data := entry.runtime_data) is None:
        # Setup failed before the controller was created.
        return unload_ok

    _LOGGER.info("Stopping Crow IP Module connection and releasing socket...")
    try:
        await hass.async_add_executor_job(runtime_data.controller.stop)
    except Exception as err:  # noqa: BLE001 - an unload must not raise
        _LOGGER.error("Error stopping controller during unload: %s", err)

    # Allow the OS and the Crow IP module to release the single TCP socket
    # before a following setup opens a new connection.
    _LOGGER.debug("Waiting 2s for TCP socket release...")
    await asyncio.sleep(2.0)
    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration after its options were changed."""
    _LOGGER.info("Options updated, reloading Crow IP Module integration...")
    await hass.config_entries.async_reload(entry.entry_id)
