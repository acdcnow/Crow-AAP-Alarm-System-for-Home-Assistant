"""Shared entity behaviour for the Crow IP Module integration.

Every entity of this integration is a push entity: it is written when the panel
reports something and when the connection state changes, and it never polls.
This mixin keeps that in one place instead of five near-identical copies.

Two things it fixes on purpose:

* **Availability follows the *reported* connection state**
  (``CrowIPAlarmPanel.connected``), not the raw socket flag. The driver retries a
  dropped link before it reports anything, so a blip that heals within a second
  does not make every entity flip to *Unavailable* and back - a state change each
  some automations act on.
* **``async_entity_id_changed`` opts in to in-place entity_id changes.**
  Home Assistant 2026.10 added ``Entity.async_prepare_to_add_to_hass`` /
  ``async_entity_id_changed``; from 2026.11 an entity whose ``entity_id`` is
  changed in the registry is updated in place instead of being removed and
  added again - but only if the integration opted in. Everything this
  integration keys on is a dispatcher signal, so ``super()`` is all that has to
  run. The lookup is defensive because the base hook only exists from 2026.11.
"""

from __future__ import annotations

from homeassistant.core import callback


class CrowConnectionEntity:
    """Mixin: connection-driven availability and dispatcher subscriptions."""

    @property
    def available(self) -> bool:
        """Return True while the panel connection is up.

        Uses the reported connection state so that a dropped link which the
        driver is already retrying does not change availability.
        """
        return bool(self._controller.connected)

    @callback
    def _connection_callback(self, _connected) -> None:
        """Re-write the entity state when the connection state changed."""
        self.async_write_ha_state()

    @callback
    def async_entity_id_changed(self, old_entity_id: str) -> None:
        """Opt in to in-place ``entity_id`` changes (Home Assistant 2026.11+).

        Only calls ``super()`` when the base class offers the hook, so this is
        safe on the Home Assistant versions that predate it.
        """
        parent = getattr(super(), "async_entity_id_changed", None)
        if callable(parent):
            parent(old_entity_id)
