# Changelog

## [Unreleased]

### 🔧 Fixed

* **Arming now completes on panels that wait for the user code.**
  `async_alarm_arm_away` / `async_alarm_arm_home` sent only `ARM ` / `STAY ` and never
  followed up with the code, so a panel programmed to expect *ARM, then code, then Enter*
  stayed disarmed. Arming now sends the arm command and then `KEYS <code>E` - the trailing
  `E` is the Enter key - which is what `2.0.0` did.
* **Disarming without a code no longer sends a bare `KEYS E`.** It now logs an error and
  does nothing instead of emitting a keypress with no digits.

### ✨ Added

* **New `Arm Sequence` option** (`arm_sequence`), offered in the setup wizard and the options
  flow and translated into all five supported languages:
  * `command_then_keypad` (**default**, matches `2.0.0`) - send `ARM ` / `STAY `, then
    `KEYS <code>E`.
  * `command_only` - send only `ARM ` / `STAY `, for panels that arm immediately and read a
    subsequent code press as a disarm.

### 📝 Documentation

* **Added `docs/ADD.md`** - Architectural Design Document: context, the six key architectural
  decisions, runtime and threading view, Home Assistant 2026.9 conformance table, quality
  attributes and a risk register.
* **Added `docs/SDD.md`** - Software Design Document: module inventory, configuration data model,
  signal contract, the full command/response protocol tables, driver internals, per-entity
  specifications, config/options flow, diagnostics, error-handling policy and traceability.
* **Added `docs/WORKFLOWS.md`** - Mermaid workflow diagrams (setup, command path, runtime data flow,
  connection lifecycle, reload, verification, release) plus the GitDiagram architecture reference.
* **README** now links the design documents, the wiki landing page and the GitDiagram map, and
  documents the arm sequence option.
* **Wiki rebuilt** around a landing page with release channels; the previous pages are preserved and
  marked as archived.

## [2.1.0-beta.1] - 2026-09-19

**Pre-release.** Targets Home Assistant **2026.9.3** (which requires Python 3.14.2+).
Users on Home Assistant 2026.8 or older should stay on `2.0.0`.

### 🔧 Fixed

* **Removed the deprecated `via_device` from `DeviceInfo`.** Home Assistant
  deprecated identifier-tuple based `via_device` in favour of `via_device_id`,
  and removes the old key in **2027.8**. The main panel is now registered in
  `async_setup_entry` before the platforms are set up, and the zone sub-devices
  (Windows / Doors / Sensors) link to it through `via_device_id`.
* **`configuration_url` is now validated before it is sent to the device
  registry.** Home Assistant rejects a `configuration_url` without an
  http(s) scheme and a host, which previously raised `ValueError` and aborted
  the device registration for hosts entered with a scheme or a path.
* **Device info is built in one place** (`device.py`). Previously six copies of
  the same `DeviceInfo(...)` block had drifted apart - some omitted
  `sw_version`, none shared the identifier constants.
* **`async_unload_entry` no longer raises** when setup failed before the
  controller existed, and `controller.stop()` is now always called through the
  executor.
* **Shutdown runs off the event loop.** The `EVENT_HOMEASSISTANT_STOP` handler
  closed the socket synchronously in the event loop.
* **Options are actually reloaded after a change** (`update_listener` is
  registered and the entry is reloaded, so renamed areas/zones/outputs and
  changed codes take effect immediately).
* **`translations/en.json` now matches `strings.json`.** The two had drifted,
  so the English options flow showed generic labels.

### 🛠 Changed

* **`hass.data[DOMAIN][entry_id]` replaced with `entry.runtime_data`**
  (`CrowRuntimeData`), the current Home Assistant pattern for per-entry state.
* **`manifest.json`:** added the required `issue_tracker`, dropped the empty
  `requirements` list, corrected the `documentation` URL and bumped the version.
* **`hacs.json`:** dropped the removed `domains` key and `iot_class` (which
  belongs in the manifest), set the minimum Home Assistant version.
* Removed leftover German/English placeholder comments and the "AI draft"
  preamble from the README.

### ✨ Added

* **Brand assets** in `custom_components/crowipmodule/brand/`
  (`icon.png` 256x256, `icon@2x.png` 512x512, and light/dark `logo.png` /
  `logo@2x.png`). Since Home Assistant 2026.3 custom integrations ship their own
  brand images and local files take precedence over the brands CDN, so no pull
  request to `home-assistant/brands` is needed.
* **Verification harnesses** under `tests/` that pin the Home Assistant 2026.9
  entity and config-flow contracts without needing Home Assistant installed.

## [2.0.0] - Refactoring for Home Assistant 2025.12+

This release marks a complete rewrite of the integration to support modern Home Assistant standards, introducing UI configuration (Config Flow) and removing the dependency on YAML configuration files.

### 💥 Breaking Changes

* **YAML Configuration Removed:** The integration no longer relies on `configuration.yaml`. Existing YAML configurations are automatically imported once, but future changes must be made via the UI.
* **Entity ID Changes:** Entity IDs may have changed due to the new naming standards.
* *Old:* `binary_sensor.crow_zone_1_kitchen` (Manual naming)
* *New:* `binary_sensor.crow_alarm_system_zone_1_name` (Automatic device naming)


* **Attributes to Entities:** System attributes (Mains Power, Battery, Tamper, Phone Line) are no longer attributes of a single sensor. They are now individual **Binary Sensors** categorized as "Diagnostic". Template sensors used to extract these values are no longer needed.

### ✨ Added

* **Config Flow (UI Setup):** Complete 4-step setup wizard:
1. **Areas:** Configure Partition names and codes.
2. **Outputs:** Configure names for switchable outputs (3 & 4).
3. **Zones:** Configure names and types for 16 zones (with Dropdown selection).
4. **Connection:** Set IP, Port, and Timeout.


* **Options Flow:** Ability to re-configure names, codes, and zone types via the "Configure" button on the integration page without restarting HA.
* **Device Registry:** All entities (Alarm Panel, Sensors, Switches) are now correctly grouped under a single device: "Crow Alarm System".
* **Translations:** Added full English (`en.json`) and German (`de.json`) translations for all configuration steps and entity names.
* **Icons:** Added specific icons for the Alarm Panel entity (`mdi:shield-home`) and Relays.
* **Import Flow:** Logic to automatically import existing settings from `configuration.yaml` to the new internal storage.

### 🛠 Changed

* **Entity Naming Standard:** Implemented `_attr_has_entity_name = True`. Entities now inherit the device name, preventing double naming (e.g., "Crow Alarm System Area A" instead of "Crow Alarm System Crow Area A").
* **Alarm Panel Logic:**
* Forced Keypad visibility (`CodeFormat.NUMBER`) to allow manual code entry even if a default code is configured.
* Refined Arming logic: Sends the arm command first, followed immediately by the code (required for Crow systems).
* Made manual code entry optional if a default code is set in the config.


* **Zone Types:** Zone types are now selected via a standardized Dropdown menu instead of free text, preventing invalid device class errors.

### 🐛 Fixed

* **Blocking I/O Error:** Fixed `Bootstrap stage 2 timeout` by moving the initial connection process (`controller.start()`) to a background executor job. Home Assistant startup is no longer blocked if the alarm panel is offline.
* **Thread Safety Crash:** Fixed `Fatal error: protocol.data_received()`. The library callbacks now use `hass.loop.call_soon_threadsafe()` to dispatch updates to the main event loop safely.
* **Attribute Error:** Fixed `AttributeError: 'CrowIPAlarmPanel' object has no attribute 'ip'`. The Host IP is now stored locally in the entity wrapper instead of relying on the library object.
* **Config Flow 500 Error:** Added robust `None`-checks and default values in the Options Flow to prevent crashes when reading empty or legacy configuration data.

### 🗑 Removed

* **Manual Template Sensors:** The need for manual template sensors in `configuration.yaml` to read battery/power status is removed. These are now native entities.
* **Deprecated Code:** Removed usage of `hass.loop` passed to the external library (deprecated in HA).
