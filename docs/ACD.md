# Architecture Concept Document (ACD)

**Project:** Crow/AAP Alarm IP Module for Home Assistant
**Integration domain:** `crowipmodule`
**Branch:** `master`
**Version:** `2.2.0b1`
**Status:** Beta
**Last updated:** 2026-10-13

---

## 1. Purpose

This document describes the **architecture** of the integration: what it is made of, why it is
shaped this way, how the parts talk to each other at runtime, and which constraints forced the
current design. It is the entry point for anyone who needs to change the integration rather than
just use it.

The companion document is the [Software Design Document (SDD)](SDD.md), which specifies the
individual modules, functions, data shapes and contracts. [WORKFLOWS.md](WORKFLOWS.md) holds the
diagrams referenced from both.

**Audience:** maintainers, contributors, and reviewers evaluating the integration against Home
Assistant's integration standards.

### 1.1 Scope

Covered:

* Command/response handling with a Crow Runner / AAP ESL-2 panel over its IP Module.
* The Home Assistant integration: config flow, entity platforms, device registry, diagnostics.
* Concurrency between Home Assistant's event loop and the panel's socket thread.

Out of scope:

* Panel firmware authoring, or any protocol behaviour the IP Module does not expose.
* Cloud access. There is none, by design (see §5.2).

---

## 2. Goals and non-goals

### 2.1 Goals

| # | Goal | How it is met |
|---|---|---|
| G1 | Work with Home Assistant **2026.10.1+** without deprecation warnings or removals | See §7 conformance table; `via_device_id`, `entry.runtime_data`, `AddConfigEntryEntitiesCallback`, `async_entity_id_changed` |
| G2 | Install cleanly through HACS with **no Python dependency** to resolve | Driver vendored under `pycrowipmodule/`; manifest `requirements` removed |
| G3 | Stay usable when the panel or network is unavailable, **without flapping** | Availability driven by the *reported* connection state; a blip is retried before it is reported; a repeated status is not dispatched; supervised reconnect with backoff |
| G4 | Report every panel signal the protocol exposes | 16 zones, 2 areas, 8 outputs, 21 system statuses |
| G5 | Be diagnosable from a user's Home Assistant instance | Downloadable diagnostics with redaction, plus a "System Status" text sensor |
| G6 | Present as a first-class integration | Local `brand/` assets, UI config flow, 5 translations, device registry (hub + one zone device) |

### 2.2 Non-goals

* **Multi-panel-per-entry.** One config entry = one IP Module. Multiple modules = multiple entries.
  (See RISK-1: unique IDs are not yet entry-scoped for every platform.)
* **A Python API for other integrations.** No custom services are registered; entity services and
  diagnostics only.
* **Historic event playback.** `MEME`/`MEMX` (memory-events) are defined in the protocol table but
  never driven by the integration.

---

## 3. Context

```
         ┌──────────────────────────┐
         │      Home Assistant      │
         │  (event loop, UI, YAML)  │
         └────────────┬─────────────┘
                      │ in-process
         ┌────────────┴─────────────┐
         │  crowipmodule (this)     │
         └────────────┬─────────────┘
                      │ TCP, ASCII lines, port 5002
         ┌────────────┴─────────────┐
         │  Crow IP Module (IA-IP)  │
         │  firmware 2.10.3628      │
         └────────────┬─────────────┘
                      │ serial bus
         ┌────────────┴─────────────┐
         │  Runner 8/16 · ESL-2     │
         └──────────────────────────┘
```

The IP Module is a serial-to-Ethernet bridge. It accepts **one** TCP client and speaks a
line-oriented ASCII protocol:

* **Commands** are `COMMAND`, `COMMAND ` or `COMMAND <argument>`, terminated `\r\n`.
* **Events** are unsolicited lines such as `ZO3` (zone 3 opened) or `MF` (mains fail).
* There is no request/response correlation, so every incoming line is matched against a pattern
  table and dispatched.

The full command and response vocabulary is specified in the SDD, §4.

---

## 4. Architectural drivers

These are the forces that determined the design. Each maps to a decision in §5.

| Driver | Consequence |
|---|---|
| The panel pushes state; it cannot be polled cheaply | Push model: `iot_class: local_push`, entities never poll (`_attr_should_poll = False`) |
| Sockets block; Home Assistant's loop must not | All socket I/O lives on one dedicated thread, never on the event loop |
| The panel accepts a single connection | Setup waits for the previous socket to be released; unload waits before returning |
| The upstream PyPI driver is unmaintained and py2/py3-era | Driver vendored, modernised, and made reload-safe |
| Home Assistant's integration contract evolves quickly | Deprecations are tracked explicitly (§7) and version-pinned via `hacs.json` |
| Panel firmware variations exist | Firmware version is captured at setup and shown as `sw_version` |

---

## 5. Key architectural decisions

### 5.1 DEC-1 — Vendor the driver instead of depending on PyPI

**Context.** The integration was originally built on the `pycrowipmodule` package (last released as
a `py2.py3-none-any` wheel). It cannot be fixed in place, and Home Assistant installations that
cannot reach PyPI fail to set up the integration at all.

**Decision.** The driver is vendored at `custom_components/crowipmodule/pycrowipmodule/` and
imported relatively (`from .pycrowipmodule import CrowIPAlarmPanel`). The manifest declares
`requirements: []` and the key is omitted entirely.

**Consequences.**

* ✔ No PyPI resolution, no version conflicts, no network dependency at install time.
* ✔ The protocol layer can be fixed alongside the integration in one commit.
* ✔ `pycrowipmodule` within the integration can never collide with an unrelated PyPI package.
* ✘ Upstream fixes no longer arrive automatically; the vendored copy must be maintained.
* ✘ HACS downloads the release archive, so `brand/` and the vendored package must stay inside
  `custom_components/crowipmodule/` (they do).

### 5.2 DEC-2 — Blocking, threaded socket rather than asyncio streams

**Context.** `asyncio.open_connection` would be the idiomatic Home Assistant choice, but the panel
is chatty, the parser is table-driven and synchronous, and the protocol has no framing beyond `\n`.

**Decision.** One worker thread (`CrowIPClientThread`) owns the socket, with a **blocking** socket
and a short read timeout (`_RECV_TIMEOUT = 5.0 s`). The timeout doubles as the keep-alive tick.

**Consequences.**

* ✔ The parser stays simple and synchronous; no `await` inside protocol handling.
* ✔ A stalled panel cannot stall the Home Assistant event loop.
* ✔ Reconnect/backoff logic is ordinary sequential code.
* ✔ The read timeout doubles as the keep-alive tick, so a dropped or silently dead socket is noticed
  within `_RECV_TIMEOUT` (5 s) without a second timer.
* ✘ Every callback must be marshalled back to the loop — the single most error-prone part of the
  design (see §6.3).
* ✘ State is read from two threads, so shared state needs discipline (see RISK-3).

### 5.3 DEC-3 — Dispatcher signals rather than a DataUpdateCoordinator

**Context.** A `DataUpdateCoordinator` is the usual Home Assistant answer for shared state, but it
models *polling*. This integration is pushed to, and entities have distinct interests (a zone only
cares about its own zone number).

**Decision.** Four topic signals plus a connection signal, declared in `const.py` and delivered with
`async_dispatcher_send` / `async_dispatcher_connect`:

| Signal | Payload | Consumers |
|---|---|---|
| `SIGNAL_ZONE_UPDATE` | zone number, or `None` for "refresh all" | `CrowZoneSensor` |
| `SIGNAL_AREA_UPDATE` | `"A"`/`"B"`, or `None` | `CrowAlarmPanel`, `CrowAlarmZoneSensor` |
| `SIGNAL_SYSTEM_UPDATE` | attribute name, or `None` | `CrowSystemSensor`, `CrowSystemStatusSensor` |
| `SIGNAL_OUTPUT_UPDATE` | output number | `CrowOutput` |
| `SIGNAL_CONNECTION_UPDATE` | `bool` | every entity (drives `available`) |

Two properties keep the churn down, and both are worth preserving when this layer is touched:

* **Only a real change is dispatched.** A handler returns `None` when the value it was given equals
  the stored one, and `_dispatch_line()` then invokes no callback. The module repeats its whole status
  after every `STATUS` probe, so without this a keep-alive probe would rewrite every entity every time.
* **Connection transitions are announced once.** `_notify_connection()` remembers the last state it
  reported and drops a repeat, so the failure of a reconnect attempt does not re-announce the outage
  that was already announced when the socket was lost.

**Consequences.**

* ✔ Entities re-read only the slice of state they need.
* ✔ `None` as the payload gives a cheap "everything changed" broadcast, used after (re)connect.
* ✘ Signal names and payload semantics are an implicit contract between `__init__.py` and the
  platforms; they are documented here and in the SDD to keep it explicit.

### 5.4 DEC-4 — `entry.runtime_data` instead of `hass.data`

**Context.** Historically the controller was stored as `hass.data[DOMAIN][entry.entry_id]`, which is
untyped, unnamespaced, and leaks if a platform fails to unload.

**Decision.** A frozen-shape dataclass travels on the config entry:

```python
@dataclass
class CrowRuntimeData:
    controller: CrowIPAlarmPanel
    entry_id: str | None = None    # config entry id, to scope registry lookups
    device_id: str | None = None   # device registry id of the hub, for via_device_id
    firmware: str | None = None    # "<version> (<date>)", for sw_version
```

**Consequences.**

* âœ” Lifetime is tied to the entry; unload cannot leak.
* âœ” One object carries every shared dependency, so platform setup is a single attribute read.
* âœ” `device_id` gives the zone sub-devices a valid `via_device_id` (see DEC-5).
* âœ” `entry_id` scopes the entity-registry lookups of the zone alignment (see DEC-7).

### 5.5 DEC-5 — Register the hub device before forwarding platforms

**Context.** Home Assistant 2026.9 deprecates identifier-tuple `via_device` in `DeviceInfo` and
**removes it in 2027.8**. Its replacement, `via_device_id`, must be a real device-registry id —
which only exists after the parent device is registered.

**Decision.** `async_setup_entry` registers the hub device itself (via `build_device_info()` and
`async_get_or_create`), stores `hub_device.id` on the runtime data, and only then calls
`async_forward_entry_setups`. All entities read `device_info` from the same helper.

**Consequences.**

* ✔ No deprecation warning; nothing breaks in 2027.8.
* ✔ Zone sub-devices (one *Crow Alarm Sensors* device for all zones) hang off the hub correctly.
* ✔ `sw_version` and `configuration_url` are consistent across all six device-info call sites
  (previously six hand-written copies had drifted).
* ✘ Setup order is now significant: the hub device must exist before any platform runs.

### 5.6 DEC-6 — Fail loudly at the entity level, never silently

**Context.** Without a connection the panel's last known state is stale. Showing it as "current" is
actively misleading for an alarm system.

**Decision.** Every entity returns `available = self._controller.connected` - the connection state the
**driver reported**, not the raw socket flag. The driver announces a disconnect only after a quick
retry failed, so a link that drops and recovers within one reconnect never changes availability at all.
The connection signal re-writes state on the transitions that do happen.

**Consequences.**

* ✔ Users and automations can distinguish "disarmed" from "unknown".
* ✔ `Diagnostics` and the System Status sensor expose `connected` explicitly.
* ✔ A brief network blip no longer produces an `unavailable` / `available` pair, which some automations
  treat as two state changes.
* ✘ A genuine outage is reported only after the immediate retry failed, i.e. up to a few seconds later
  than the socket actually dropped. For an alarm panel that trade is the right way round.
### 5.7 DEC-7 â€” One device for all zone entities

**Context.** Releases 2.1.x gave every zone type its own device (*Crow Alarm Windows*, *Crow Alarm
Doors*, *Crow Alarm Motion*, ...) so that the type became part of the entity name and entity id.
That turned out to be a trap: Home Assistant links an entity to a device **only when the entity is
registered for the very first time**. An entity created while a zone still had another type stayed on
the device of that former type, and re-configuring the zone in the UI did not move it - the device
list kept showing a door zone under *Windows* with no way to correct it from the UI.

**Decision.** All zone entities are registered on the single *Crow Alarm Sensors* device
(`const.IDENTIFIER_ZONE`). The zone type still selects the binary-sensor **device class** (the icon:
door, window, motion, smoke, ...), but never the device. `binary_sensor._async_align_zone_entities()`
re-links existing zone entities to that device on every setup, so an installation that has been
through the split layout is corrected by a restart, and
`_remove_retired_zone_devices()` deletes the retired per-type devices once nothing is registered on
them.

**Consequences.**

* âœ” There is no second device left for a zone to be stuck on, whatever order zones were configured
  or re-typed in.
* âœ” Entity ids are never rewritten by the integration: they are stable handles for dashboards and
  automations, and a zone that keeps its id keeps working after the move.
* âœ˜ An entity id may still name a device the entity no longer hangs off
  (`binary_sensor.crow_alarm_windows_terrassentur` on *Crow Alarm Sensors*). That is cosmetic; the
  diagnostics `zone_registry` report shows the real device link.
* âœ˜ The type is no longer visible in the device name, so the icon and the entity name carry it.

### 5.8 DEC-8 - Calm the connection: report transitions, not events

**Context.** In 2.2.0 and earlier an installation could go *Unavailable* and back to *connected* every
few minutes, and every cycle rewrote the state of every entity. Three separate mechanisms fed it:

1. the shipped keep-alive of **300 s** is longer than the IP module's own idle timeout, so the module
   closed the socket first and the integration reconnected (and re-dumped the full status) on a timer
   it did not control;
2. a disconnect was announced immediately, and a failed reconnect attempt announced it *again*, even
   though a reconnect a second later undid it;
3. every line of the status dump was forwarded, so the repeated values in it rewrote every entity,
   and connect additionally broadcast a redundant refresh 2 s later.

**Decision.** Treat the connection as a *state* rather than a stream of events:

* a link that had been up for `_STABLE_CONNECTION` (5 s) is retried once before a disconnect is
  announced - a blip that heals produces no signal at all;
* a link that flaps faster than that is a real failure and goes through the backoff, so a panel that
  accepts and immediately drops cannot be hammered;
* `_notify_connection()` forwards a state only when it differs from the last reported one;
* a handler returns `None` when the value is unchanged, and `_dispatch_line()` then calls nothing;
* the post-connect broadcast is removed - the `STATUS` dump on connect already carries the full state;
* the keep-alive default becomes the panel driver's own **30 s**, is validated in the flow
  (15-3600 s) and clamped in the driver, and existing entries are migrated (config entry version 2).

**Consequences.**

* ✔ A healthy panel with a stable network produces **no** state writes between real events.
* ✔ A brief interruption is invisible to Home Assistant, so automations no longer fire twice.
* ✘ An outage is reported a few seconds late (after the immediate retry failed), and an entry that
  relied on a 300 s keep-alive is moved to 30 s by the migration.
* ✘ The driver now carries state (`_reported_connected`) instead of being a pure pass-through, which
  must be kept in mind when it is changed.

---

## 6. Runtime view

### 6.1 Component decomposition

```
custom_components/crowipmodule/
├── __init__.py            Entry setup/teardown, callback marshalling, hub device registration,
│                          config-entry migration (keep-alive normalisation)
├── device.py              CrowRuntimeData, configuration_url(), build_device_info()
├── entity.py              CrowConnectionEntity - connection-driven availability,
│                          connection subscription, in-place entity_id opt-in        [NEW]
├── const.py               Domain, option keys, limits, defaults, signal topics, device ids
├── config_flow.py         Config flow (5 steps) and options flow (4 steps)
├── alarm_control_panel.py CrowAlarmPanel  - Arm Away / Home, Disarm, Trigger
├── binary_sensor.py       CrowZoneSensor, CrowSystemStatusSensor
├── button.py              CrowChimeButton, CrowRelayButton
├── sensor.py              CrowSystemSensor (status text), CrowAlarmZoneSensor (last alarm)
├── switch.py              CrowOutput
├── diagnostics.py         Redacted config-entry diagnostics
├── manifest.json          domain, version, documentation, issue_tracker, iot_class
├── strings.json           English source strings (mirrored to translations/en.json)
├── translations/          de, en, es, fr, it
├── brand/                 icon.png, icon@2x.png, logo.png, logo@2x.png, dark_logo…    [NEW]
└── pycrowipmodule/        Vendored driver
    ├── __init__.py        Re-exports CrowIPAlarmPanel, CrowIPModuleClient
    ├── alarm_panel.py     CrowIPAlarmPanel - facade, state accessors, callback properties
    ├── crow_base_client.py CrowIPModuleClient - thread, reconnect, parser, command builders
    ├── crow_defs.py       COMMANDS, RESPONSE_FORMATS tables
    └── status_state.py    Initial state factories
```

### 6.2 Setup workflow

See [WORKFLOWS.md §2](WORKFLOWS.md#2-entry-setup-workflow).

### 6.3 Threading and loop safety

This is the crux of the design, so it is stated explicitly:

```
Panel thread                             Home Assistant event loop
────────────                             ─────────────────────────
socket.recv() ──► _dispatch_line()
   │                    │
   │              handle_*_state_change()   (mutates panel.<x>_state)
   │                    │
   │              callback_*_state_change(data)
   │                    │
   └──── hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, SIGNAL, data) ──►
                                              │
                                     entity._update_callback(data)
                                              │
                                     self.async_write_ha_state()
```

Rules that follow from this:

1. **Never touch Home Assistant state from the panel thread.** Only `call_soon_threadsafe`.
2. **Panel state dicts are the shared memory.** The panel thread writes, the loop reads.
3. **Coroutines scheduled from the thread use `asyncio.run_coroutine_threadsafe`**, not
   `loop.create_task` (which is not thread-safe). The connection-announcement delay uses this.
4. **`async_write_ha_state()` is loop-only** and is never called from a callback that has not been
   marshalled first.

### 6.4 Connection lifecycle

See [WORKFLOWS.md §4](WORKFLOWS.md#4-connection-lifecycle). Summary:

`_connect()` → `_notify_connection(True)` → `request_status()` → `_listen_loop()`. When the socket
is lost, a link that had been up for at least `_STABLE_CONNECTION` (5 s) is **retried once,
immediately** - if that retry succeeds the outage is never announced. Only when it keeps failing is
`_notify_connection(False)` sent, followed by the backoff (10 s, doubling, capped 60 s).
`_notify_connection()` is idempotent: it forwards a state only when it differs from the last one it
reported, so a repeated failure cannot re-write every entity. `stop()` sets a flag, wakes the loop
and closes the socket.

### 6.5 Command path

See [WORKFLOWS.md §3](WORKFLOWS.md#3-user-command-workflow). Entity → `CrowIPAlarmPanel` facade →
`CrowIPModuleClient` → `send_command()` (table lookup in `COMMANDS`, argument formatting) →
`send_data()` (append `\r\n`, `sendall` under a lock). A send failure drops the connection so the
supervisor reconnects rather than writing into a dead socket.

---

## 7. Home Assistant conformance (2026.10.1)

Verified against the real 2026.10 sources; each row is asserted by
`tests/verify_ha_2026_contract.py`.

| Requirement | Implementation |
|---|---|
| `DeviceInfo` uses `via_device_id`, not `via_device` (removed 2027.8) | `device.py::build_device_info` |
| `configuration_url` must be `http(s)` with a host | `device.py::configuration_url()` normalises and drops unusable values |
| Per-entry state via `entry.runtime_data` | `CrowRuntimeData` on the config entry |
| Platform callbacks typed `AddConfigEntryEntitiesCallback` | every `async_setup_entry` |
| Entities do not poll | `_attr_should_poll = False` on all base classes |
| `AlarmControlPanelEntity.alarm_state` (not the legacy `state`) | `CrowAlarmPanel.alarm_state` |
| `EntityCategory` from `homeassistant.const` | `binary_sensor.py`, `sensor.py` |
| `strings.json` mirrored in `translations/en.json` | asserted by `tests/verify_config_flow.py` |
| `manifest.json` needs `domain`, `documentation`, `issue_tracker`, `codeowners`, `name`, `version` | `manifest.json` |
| Brand images may ship locally (HA 2026.3+) | `brand/` |
| `Entity.async_entity_id_changed` opt-in for in-place `entity_id` changes (hook from 2026.10, default from 2026.11) | `entity.py::CrowConnectionEntity.async_entity_id_changed` calls `super()` defensively |
| Config-entry migrations may normalise stored data (`async_migrate_entry`, version 1 → 2) | `__init__.py::async_migrate_entry` normalises `keepalive_interval` |
| Python 3.14.2+ (HA 2026.10 floor) | declared in `hacs.json` |

---

## 8. Quality attributes and how they are addressed

| Attribute | Mechanism | Trade-off accepted |
|---|---|---|
| **Availability** | `available` from the *reported* connection state; a blip is retried before it is reported; reconnect with backoff | A genuine outage is reported only after the first retry fails |
| **Reliability** | Send failure drops the socket; unload and setup both wait for socket release | ~2 s pause on reload |
| **Responsiveness** | Push-only; no polling; sub-second state propagation | UI updates depend on panel event rate |
| **Diagnosability** | Structured debug logs (`TX:`/`RX:`), diagnostics dump, status sensor | Verbose at debug level |
| **Security** | No cloud, no telemetry; area codes and host redacted in diagnostics | Panel credentials stored in the config entry |
| **Testability** | Protocol layer testable with no Home Assistant; HA contracts pinned by stub harnesses | Harnesses are not a substitute for a live panel |
| **Maintainability** | One device-info helper; single source for constants; vendored driver | Diverges from PyPI upstream |

---

## 9. Deployment view

```
<config>/custom_components/crowipmodule/
```
Installed by HACS from GitHub release archive `2.2.0b1` (or the branch), or copied manually.
Home Assistant imports the package at startup; the config entry lives in
`.storage/core.config_entries`, not in YAML. Per-entry runtime objects are constructed at setup and
released at unload.

---

## 10. Risks and open items

| ID | Risk | Impact | Mitigation / status |
|---|---|---|---|
| RISK-1 | Unique IDs for zones/sensors/outputs/buttons are global (`crow_zone_1`), not entry-scoped. Two IP Modules collide; HA logs *"ID already used by … - ignoring"* | Multi-panel users lose entities | **Open.** Needs a migration (new IDs orphan existing entities). The alarm panel is already scoped as `{entry_id}_crow_area_N`. |
| RISK-2 | Setup blocks ~4 s (`asyncio.sleep(2.0)` twice) | Slow startup | **Open, accepted.** Workaround for the panel's single-socket behaviour; could be replaced by an active readiness probe. |
| RISK-3 | `_is_connected` is read from several threads without a lock | Theoretically stale reads | **Low.** CPython attribute assignment is atomic. `_reported_connected` - the value availability actually follows - *is* guarded by `_state_lock`, because two threads may report a transition at once. |
| RISK-4 | No `async_step_import` exists and no `CONFIG_SCHEMA` is defined, so the integration cannot be configured from YAML | Nothing to migrate; no YAML path at all | **Accepted.** UI-based code is always created directly by the user. |
| RISK-5 | Vendored driver will drift from upstream | Missing upstream fixes | **Accepted** by DEC-1; upstream is effectively dormant. |
| RISK-6 | `hacs.json` pins `homeassistant: 2026.10.1`, so this release will not install on 2026.9 or older | Blocks older installs | **Deliberate.** 2026.10.1 is the tested floor; the entity lifecycle hook this release adopts is 2026.10+. |
| RISK-7 | No live-hardware CI | Regressions only surface with a real panel | Mitigated by the protocol self-test and stub harnesses. |

---

## 11. Document map

| Document | Audience | Contents |
|---|---|---|
| [ACD](ACD.md) (this) | Maintainers, reviewers | Architecture, decisions, runtime view, risks |
| [SDD](SDD.md) | Implementers | Modules, signatures, data models, protocol tables, entity contracts |
| [WORKFLOWS](WORKFLOWS.md) | Everyone | Mermaid diagrams: setup, data flow, commands, lifecycle, verification |
| [Wiki — HA 2026.09 dev branch](https://github.com/acdcnow/Crow-AAP-Alarm-System-for-Home-Assistant/wiki/HA-2026.09-Development-Branch) | Users | What changed and how to install it |
| [Wiki — archived docs](https://github.com/acdcnow/Crow-AAP-Alarm-System-for-Home-Assistant/wiki/Archived-Documentation) | Users on old releases | Preserved 1.x design documents |

---

## 12. Glossary

| Term | Meaning |
|---|---|
| **Area** | Panel partition (A/B). Becomes an `alarm_control_panel` entity. |
| **Zone** | A sensor input on the board (1–16). Becomes a `binary_sensor`. |
| **Output / PGM** | A switched board output. Exposed as a `switch`; toggled by the `OO<n>` command. |
| **Relay** | `RL1`/`RL2` momentary activation. Exposed as a `button`. |
| **IP Module** | The serial↔Ethernet bridge the integration talks to. |
| **Keep-alive** | Periodic `STATUS` request that both refreshes state and detects a dead socket. |
| **Dispatcher signal** | Home Assistant's in-process pub/sub used to notify entities. |
