# Changelog

## [2.2.0-beta.1] - 2026-10-10

> ⚠️ **Pre-release - enable *Show beta versions* in HACS to test it.**

**All zone entities now live on one device** (`Crow Alarm Sensors`) instead of one device per zone
type. Home Assistant links an entity to a device only when it is registered for the very first time,
so the split layout could leave an entity behind on the device of a type the zone no longer had - and
no amount of re-configuring would move it. With a single device there is nothing left to be assigned
to the wrong place.

### 🛠 Changed

* Zone entities are registered on `Crow Alarm Sensors` (`crow_sensors`). The zone **type** still
  decides the binary-sensor device class and therefore the icon (*Fenster*, *Tür*, *Bewegung*, ...);
  it no longer decides which device the entity hangs off.
* On every setup the integration moves already-registered zone entities onto that device, so an
  installation that has been through 2.0.0 - 2.1.4 is corrected on the next restart.
* **Entity ids are no longer rewritten.** An entity id is a handle your dashboards and automations
  point at; it stays exactly as it is (`binary_sensor.crow_alarm_windows_terrassentur` keeps working
  even though the entity now sits on *Crow Alarm Sensors*). Newly created entities get
  `binary_sensor.crow_alarm_sensors_<name>`.
* The per-type devices (*Crow Alarm Windows*, *Crow Alarm Doors*, *Crow Alarm Motion*, ...) are
  **removed from the device registry once nothing is registered on them any more**. A device that
  still has entities is never touched.
* The diagnostics `zone_registry` report now shows `Crow Alarm Sensors` as the expected device and
  reports the device each entity is really registered on.

### ℹ️ What to expect on update

* After the restart the log lists one line per moved zone
  (`Zone 4 'Küchenfenster' (window) moved from device ... to 'Crow Alarm Sensors' (entity id unchanged: ...)`),
  and one line per retired device it removed.
* **No configuration change is needed** - no re-adding of zones or the integration.

## [2.1.4] - 2026-10-10

Makes the zone → device → entity assignment observable, so a zone that is grouped under another
type's device can be diagnosed from the log and from the diagnostics download alone. No behaviour
change beyond that: the repairs from 2.1.3 are unchanged.

### ✨ Added

* **`zone_registry` in the diagnostics download** (Settings → Devices & Services → the integration →
  ⋮ → *Download diagnostics*). Per zone it lists the configured `name` and `type` next to the device
  the entity is *actually* registered on - `entity_id`, `device_id`, `device_name`,
  `device_identifiers` - plus the device/identifier the type expects. The device an entity is linked
  to is not shown anywhere in the Home Assistant UI, which makes this the quickest way to see
  whether an entity sits where its type says it should.

### 🛠 Changed

* The zone alignment now logs the device it resolved for **every** zone at `DEBUG`
  (`Zone 4 'Küchenfenster' (window) -> device 'Crow Alarm Windows', entity
  binary_sensor.crow_alarm_windows_kuchenfenster`) and an `INFO` line whenever it moves or renames
  one, so a setup that changed nothing is distinguishable from one that repaired something.
* The type → device mapping has a single accessor (`const.zone_device()`), used by the
  binary-sensor platform and by diagnostics.

> **Nothing to configure.** Update, restart once, and - if a zone still shows up under the wrong
> device - send the `Zone types: ...` and `Zone N ... -> device ...` log lines or the diagnostics
> download.

## [2.1.3] - 2026-10-10

Repairs the zone devices and entity ids of installations whose zones were re-typed after
their entities had been created, and rewrites the zone part of the config/options flow.
Supersedes `2.1.2` (published and withdrawn the same day).

### 🔧 Fixed

* **A zone device now carries its own name for good.** Home Assistant uses the name a
  device was *created* with - a later `name` in the device info is ignored - and it builds
  an entity id from that name. A group device that was created by an older build with the
  other type's name therefore kept handing that name to every entity id generated from it,
  which is how a window zone ends up as `binary_sensor.crow_alarm_doors_<name>` and shows
  up under the doors device. The integration now compares the name of each zone device with
  the name its type requires and corrects it (an integration name is updated, a name you
  set yourself is never touched), logging the correction.
* **Existing zone entities follow their zone's type.** An entity is linked to a device - and
  gets its entity id - only when it is registered for the **first time**; afterwards Home
  Assistant fixes the `device_id` at most, never the entity id. On every setup the
  integration now re-derives the device from the configured type and rebuilds the entity id
  when it was generated for another zone type's device, so
  `binary_sensor.crow_alarm_windows_terrassentur` becomes
  `binary_sensor.crow_alarm_doors_terrassentur`. An id you chose yourself is moved but never
  renamed, and every correction is logged.
* **The zone list is logged on every setup** (`Zone types: 1 'Eingangstür'=door, ...`), so a
  zone that is grouped unexpectedly can be traced to the type that is actually stored for it.

### 🛠 Changed

* **The zone step of the config and options flow was rewritten.** All zones are configured
  in **one** step instead of pages of four, so there is no page counter any more that a form
  submission could get out of sync with.
* The zone **type** is now a translated dropdown (*Fenster*, *Tür*, *Bewegung*, ...) instead
  of the raw values `window` / `door` / `motion`.
* Each field is mapped back by its own name (`zone_7_type` -> zone `7`), so a value can only
  ever be stored on the zone it was entered for, and zones that are not part of the form keep
  the value they have instead of being dropped.

> **After updating:** restart Home Assistant once so the devices and entities are corrected -
> the log then shows the `Zone types: ...` line and one line per correction. Zones whose type
> is still wrong can now be fixed in **Configure** (the type dropdown is the second field of
> each zone); saving moves and renames the entity automatically.

## [2.1.2] - 2026-10-10

### 🔧 Fixed

* **Zone sub-devices are grouped per zone type.** A zone is registered on the device that
  matches its **configured type**: `window` -> *Crow Alarm Windows*, `door` ->
  *Crow Alarm Doors*, `motion` -> *Crow Alarm Motion*, `smoke` -> *Crow Alarm Smoke*, and
  likewise for `gas`, `co`, `tamper` and `safety`, so the type is part of the device name and
  - through `has_entity_name` - of the entity name and entity id.
* Grouping reads the zone type directly (`const.ZONE_DEVICES`) instead of deriving it from the
  binary-sensor device class, so the two can no longer drift apart.

### 🛠 Changed

* Previously every zone that was not a window or a door (motion, smoke, gas, CO, tamper,
  safety) was lumped onto a single *Crow Alarm Sensors* device. Each type now has its own
  device. *Crow Alarm Sensors* remains as the fallback for an unknown type, and the
  `crow_windows` / `crow_doors` identifiers are unchanged, so the doors and windows devices
  are picked up as-is on update.
* Zone types are now declared once, in `const.py` (`ZONE_TYPES`, `ZONE_DEVICES`), and consumed
  by the config flow and the binary-sensor platform.
* **New brand images.** `icon.png` / `icon@2x.png` (256x256 / 512x512) and
  `logo(.dark)?(_@2x)?.png` (342x160 / 684x320) were rebuilt from the current project banner.
  The whole artwork is shown: it is scaled into the canvas and the strips the different aspect
  ratio leaves over are filled with a continuation of the banner's own background (the edge
  band is mirrored and faded towards the rim).

## [2.1.1] - 2026-10-09

### 🛠 Changed

* **New brand images, built from the project banner.** The **whole** artwork is
  shown now: it is scaled into the logo canvas, and the strips the different
  aspect ratio leaves over are filled with a continuation of the banner's own
  background (the picture's edge band is mirrored and faded out towards the
  rim), so nothing is cut off and no seam is visible. `icon.png` / `icon@2x.png`
  (256x256 / 512x512), `logo.png` / `logo@2x.png` (342x160 / 684x320) and the
  matching `dark_logo*` files were all replaced.

No code change - this release only refreshes the assets HACS and the README
show.

## [2.1.0] - 2026-09-30

First **stable** release of the Home Assistant 2026.9 line. It contains
`2.1.0-beta.1` and `2.1.0-beta.2` unchanged, plus the additions below - update
from either beta.

Targets Home Assistant **2026.9.3** (which requires Python 3.14.2+). Users on
Home Assistant 2026.8 or older should stay on `2.0.0`.

### ✨ Added

* **A ready-to-use Lovelace dashboard** (`dashboards/alarm-dashboard.yaml`): a
  standard view (arming, doors, windows, motion) and an expert view (panel
  diagnostics, classic keypad with a guarded panic trigger, 72 h event log, 24 h
  zone history) switched with a single `input_boolean.expert_mode`. Conditional
  banners cover alarm, panel fault and exit delay. No packages, no template
  sensors and no custom cards - not even a helper beyond the view switch, every
  summary is computed by the cards themselves.
* **Offline dashboard preview** (`dashboards/preview/`): renders the exact card
  tree from the YAML - `cards.js` is generated from it, not maintained by hand -
  with the real Home Assistant theme tokens, including the visibility rules on
  cards and sections, the tile colour logic and the Jinja in the markdown cards.

### 📝 Documentation

* README: release banner for `2.1.0`, a new Dashboard section with screenshots,
  and the real repository URL in the HACS instructions (it still contained the
  `YOUR_USERNAME/YOUR_REPO_NAME` placeholder, so following them literally added
  a non-existent repository).
* README: **corrected the Custom Bypass claim.** The integration never offered
  it - `supported_features` is `ARM_HOME | ARM_AWAY | TRIGGER`, and there is no
  bypass service or button - so both the feature bullet and the "To Bypass"
  instructions described something that does not exist. They now state that the
  panel reports the bypass state per zone (`bypass` attribute, fed by the
  panel's `ZBY` / `ZBYR` messages) but that setting it is not possible from
  Home Assistant.
* New `dashboards/README.md`: install steps, entity ids, the offline preview and
  a table of the defects the new dashboard fixes in the previous one.

### 🔧 Fixed

* Manifest and README now report `2.1.0` instead of `2.1.0-beta.2`. HACS
  compares the tag against the manifest version, so a stable tag with a
  pre-release manifest version never matched.
* **CI**: the generic `Python application` workflow that shipped with the
  repository is replaced by `.github/workflows/verify.yml`. The old one pinned
  Python 3.10 (this integration targets Home Assistant 2026.9, which requires
  3.14.2+) and ran `pytest` over a repository that contains no pytest tests, so
  it could only ever fail. The new workflow runs the project's harnesses on
  Python 3.14.
* **`hacs.json` no longer sets `zip_release`.** The key was inherited from the
  old `master` line (added there on 2026-09-14) and had no `filename` next to
  it. HACS rejects exactly that combination - "zip_release is True, but
  filename is not set" - and the download step then called `endswith` on the
  missing filename, so **every** install and update failed with
  `Failed to perform the action update/install. 'NoneType' object has no
  attribute 'endswith'`. An integration ships its source rather than a release
  asset, so the key is not needed at all. `tests/verify_hacs_manifest.py` now
  validates `hacs.json` and `manifest.json` against HACS's own schemas, and CI
  runs it, so this cannot come back unnoticed.

  > The `2.1.0` tag was moved onto this fix (and then again onto the cleanup
  > below) and the release was published again. HACS downloads by tag, so a
  > repository that was already fetched needs *Redownload* (or *Update*, if HACS
  > still offers it) after refreshing the repository list.
* **Removed the content the release merge had pulled in from the old `master`
  line.** The promotion used `-X theirs`, which only resolves *conflicting*
  hunks - changes the old line had made to *other* lines of the same file merged
  in silently. The release therefore carried text the `HA2026_09_dev` line never
  had:

  * `info.md` - large parts replaced by the 1.1.x description, including a
    version badge that read `1.1.4`. HACS renders this file as the integration's
    info panel.
  * `README.md` - a duplicated "Manual Installation" step list and a stray
    "### 2. Device Quantities" section.
  * `alarm_control_panel.py`, `binary_sensor.py`, `config_flow.py` - two stray
    comments and a removed blank line (no functional change).
  * `.github/workflows/python-app.yml` - the generic CI template, replaced by
    `verify.yml` (see above).

  All of it is restored from `HA2026_09_dev`. The tree now differs from that
  branch only by the CI workflow, this changelog,
  `tests/verify_hacs_manifest.py` and `LICENSE`.
* **`LICENSE` is the GPL-3.0 file**, not the MIT file the 2.x development line
  carried: the old `master` line added GPL-3.0 on 2026-09-23 and GitHub already
  reported the repository as GPL-3.0, so nothing changes for HACS. Note however
  that `2.0.0` and the `2.1.0-beta` releases were published under MIT - restore
  that with `git checkout 2.0.0 -- LICENSE` if MIT is the intended licence.

## [2.1.0-beta.2] - 2026-09-21

**Pre-release.** Targets Home Assistant **2026.9.3** (which requires Python 3.14.2+).
Users on Home Assistant 2026.8 or older should stay on `2.0.0`.

Restores arming on panels that expect the user code after the arm command, and makes that
behaviour configurable - `2.1.0-beta.1` could not arm such a panel at all.

### 🔧 Fixed

* **Arming now completes on panels that wait for the user code.** `async_alarm_arm_away` /
  `async_alarm_arm_home` sent only `ARM ` / `STAY ` and never followed up with the code, so a
  panel programmed to expect *ARM, then code, then Enter* stayed disarmed. Arming now sends the
  arm command and then `KEYS <code>E` - the trailing `E` is the Enter key - which is what
  `2.0.0` did. `send_keypress()` and `disarm()` produce the same wire line, which is why the
  follow-up had been mistaken for a disarm.
* **Disarming without a code no longer sends a bare `KEYS E`.** It now logs an error and does
  nothing instead of emitting a keypress with no digits.

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

### 🧪 Verification

Both stub-HA harnesses cover the new option: `tests/verify_ha_2026_contract.py` asserts the emitted
wire sequence for both modes (including the `KEYS <code>E` follow-up, the disarm path and option
precedence over `entry.data`); `tests/verify_config_flow.py` asserts the selector's options, its
translation key and that every language translates every mode.

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
