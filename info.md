# Crow/AAP Alarm IP Module

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Maintainer](https://img.shields.io/badge/maintainer-acdcnow-blue)](https://github.com/acdcnow)
[![Version](https://img.shields.io/badge/version-1.1.4-green)]()

**A robust Home Assistant integration for Crow Runner and AAP (Arrowhead Alarm Products) alarm systems via the IP Module.**

This integration provides local, real-time control and monitoring of your alarm system without relying on cloud services.
This is a custom component for Home Assistant to integrate **Crow Runner** alarm systems equipped with the **IP Module** (IA-IP-MODULE) running Firmware Ver 2.10.3628 2017 Oct 20 09:48:43.

## ✨ Features

* **Config Flow:** Fully configurable via the Home Assistant UI (no YAML required).
* **Alarm Control Panel:** Arm (Away/Stay), Disarm, and Trigger panic alarms for up to 2 Areas (Partitions).
* **Zones:** Binary sensors for up to 16 zones (Motion, Door, Window, Smoke, etc.).
* **Outputs:** Control up to 2 switchable outputs (e.g., Garage Door, Gates).
* **System Status:** Diagnostic sensors for Mains Power, Battery, Tamper, Phone Line, and Dialler status.
* **Device Registry:** All entities are grouped under a single "Crow Alarm System" device.
* **Dashboard:** a ready-to-use Lovelace dashboard with a standard and an expert view ships in [`dashboards/`](dashboards/README.md).

## 📋 Requirements

* **Home Assistant:** Version 2026.09.0 or newer.
* **Hardware:** Crow Runner or AAP control panel with an installed IP Module.
* **Network:** The IP Module must be connected to the same network as Home Assistant.

## 🚀 Installation

### Option 1: HACS (Recommended)

1. Open HACS in Home Assistant.
2. Go to "Integrations" > Top right menu > "Custom repositories".
3. Add the URL of this repository.
4. Category: **Integration**.
5. Click **Install**.
6. Restart Home Assistant.

### Option 2: Manual Installation

1. Download this repository.
2. Copy the `custom_components/crowipmodule` folder into your Home Assistant's `config/custom_components/` directory.
3. Restart Home Assistant.

## ⚙️ Configuration

Setup is handled entirely through the Home Assistant UI.

1.  Go to **Settings** > **Devices & Services**.
2.  Click **Add Integration** and search for **Crow/AAP Alarm IP Module**.
3.  **Connection:** Enter the IP address and port (default `5002`) of your IP Module.
4.  **Areas:** Select if you use 1 or 2 areas and name them.
5.  **Outputs:** Name your 2 outputs (Output 1 & Output 2).
6.  **Zones:** Configure up to 16 zones across multiple pages (4 zones per page). You can assign custom names and select the specific device class (e.g., `window`, `motion`, `smoke`) for proper icon and state representation in Home Assistant.

---

## 🎮 Entities Created

Once configured, the integration will create the following entities:

* **Alarm Control Panel:** `alarm_control_panel.area_1` (and `area_2` if enabled).
* **Switches:** `switch.output_1` and `switch.output_2`.
* **Binary Sensors:**
    * One sensor for each configured Zone (e.g., `binary_sensor.kitchen_window`).
    * System sensors: `Mains Power`, `System Battery`, `Tamper`, `Phone Line`, `Dialler`.
* **Sensor:** A text sensor showing the raw status message from the panel (e.g., "Ready", "Mains Failure").

---

## ⚠️ Important Notes

1.  **Single Connection:** The IP Module hardware typically supports only **one** active TCP connection. Ensure no other software (like the Crow configuration tool) is connected to the module while Home Assistant is running.
2.  **Reloading:** If you reload the integration, there is a safety delay of 2 seconds to allow the previous network socket to close cleanly before reconnecting.
3.  **Initial State:** After a restart, the entity states might show as "Unknown" for a few seconds until the alarm panel sends its full status dump.

---

## 🐛 Troubleshooting


### Migration from YAML

If you previously used the YAML configuration, the integration will automatically import your settings (Zones, Areas, IP) upon the first restart. Once the device appears in the "Integrations" dashboard, you can safely remove the `crowipmodule:` section from your `configuration.yaml`.

## 🛡️ Usage

### Alarm Panel

* **Arming:** Click "Arm Away" or "Arm Home". If a code is required and not saved in the config, the keypad will appear.
* **Disarming:** Enter your code on the keypad and click "Disarm".
* **Keypad:** The keypad is always available to send manual commands or codes.

### Diagnostic Sensors

System health information is located on the Device page under the **Diagnostic** category. These sensors indicate problems (e.g., "Low Battery" or "Power Failure").

* `Mains Power` (On = Power OK)
* `System Battery` (On = Battery Low)
* `System Tamper` (On = Tamper Detected)

### Outputs

Outputs 1 & 2 are usually hardware relays on the board. Outputs 3 & 4 are the controllable switches configured during setup. They appear as standard Switch entities in Home Assistant.

Here is a detailed **CHANGELOG** summarizing the refactoring from the original YAML-based code to the new Home Assistant 2025-compliant integration.

# Changelog

## [2.0.0] - Refactoring for Home Assistant 2026.09+

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


## 🔧 Troubleshooting

**Enable Debug Logging:**
If you encounter issues, enable debug logging to see the raw communication with the module.

Add this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.crowipmodule: debug
    pycrowipmodule: debug

## Credits

Based on the `pycrowipmodule` library.
Original custom component author: @febalci.
Refactored for Home Assistant 2025+ with Config Flow support.
