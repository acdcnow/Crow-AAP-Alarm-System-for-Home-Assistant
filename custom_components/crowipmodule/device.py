"""Device registry helpers and runtime data for the Crow IP Module integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    IDENTIFIER_HUB,
    MANUFACTURER,
    MODEL_IP_MODULE,
)

if TYPE_CHECKING:
    from .pycrowipmodule import CrowIPAlarmPanel


@dataclass
class CrowRuntimeData:
    """Objects shared between a config entry and its entity platforms."""

    controller: CrowIPAlarmPanel
    #: Device registry id of the main panel, used as ``via_device_id`` for the
    #: zone sub-devices. ``None`` while the hub device has not been registered.
    device_id: str | None = None
    #: Firmware string reported to the device registry, e.g.
    #: ``"Ver 2.10.3628 2017 (Oct 20 09:48:43)"``.
    firmware: str | None = None


def configuration_url(host: str | None) -> str | None:
    """Return a valid device registry ``configuration_url`` for a host.

    Home Assistant validates that ``configuration_url`` is an ``http``/``https``
    URL that contains a host. A bare IP address is normalised, and anything
    unusable is dropped instead of raising ``ValueError`` while the device is
    being registered.
    """
    if not host:
        return None
    host = host.strip()
    if not host:
        return None
    url = host if "://" in host else f"http://{host}"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return url


def build_device_info(
    *,
    name: str,
    host: str | None = None,
    identifier: str = IDENTIFIER_HUB,
    model: str = MODEL_IP_MODULE,
    sw_version: str | None = None,
    via_device_id: str | None = None,
) -> DeviceInfo:
    """Build the ``DeviceInfo`` for one of the integration's devices.

    ``via_device_id`` must be the device registry *id* of an already registered
    device in the same config entry. The older ``via_device`` identifier tuple
    is deprecated in Home Assistant and is removed in 2027.8.
    """
    info: DeviceInfo = {
        "identifiers": {(DOMAIN, identifier)},
        "name": name,
        "manufacturer": MANUFACTURER,
        "model": model,
    }
    if sw_version:
        info["sw_version"] = sw_version
    if url := configuration_url(host):
        info["configuration_url"] = url
    if via_device_id:
        info["via_device_id"] = via_device_id
    return info
