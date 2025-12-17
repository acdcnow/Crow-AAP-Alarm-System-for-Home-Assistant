# Changelog

## [1.0.0] - Refactoring for Home Assistant 2025.12+

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
