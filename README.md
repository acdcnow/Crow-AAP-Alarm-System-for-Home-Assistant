Here is a comprehensive `README.md` file for your GitHub repository. It documents the new Config Flow, the migration process, and how to use the integration.

---

# Crow/AAP Alarm IP Module for Home Assistant

This is a custom component for Home Assistant to integrate **Crow Runner** and **AAP (Arrowhead Alarm Products)** alarm systems equipped with the **IP Module** (IA-IP-MODULE) running Firmware Ver 2.10.3628 2017 Oct 20 09:48:43.

It communicates directly with the IP module over the local network to provide real-time status updates and control.

## ✨ Features

* **Config Flow:** Fully configurable via the Home Assistant UI (no YAML required).
* **Alarm Control Panel:** Arm (Away/Stay), Disarm, and Trigger panic alarms for up to 2 Areas (Partitions).
* **Zones:** Binary sensors for up to 16 zones (Motion, Door, Window, Smoke, etc.).
* **Outputs:** Control up to 2 switchable outputs (e.g., Garage Door, Gates).
* **System Status:** Diagnostic sensors for Mains Power, Battery, Tamper, Phone Line, and Dialler status.
* **Device Registry:** All entities are grouped under a single "Crow Alarm System" device.

## 📋 Requirements

* **Home Assistant:** Version 2025.12.3 or newer.
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

This integration uses a 4-step configuration wizard.

1. Go to **Settings** > **Devices & Services**.
2. Click **+ Add Integration**.
3. Search for **Crow/AAP Alarm IP Module**.

### The Setup Wizard

* **Step 1: Areas**
* Name your partitions (e.g., "House", "Garage").
* (Optional) Enter a default code if you want to arm/disarm without typing it every time.


* **Step 2: Switches (Outputs)**
* Name your controllable outputs (Output 3 & 4), e.g., "Garage Door".


* **Step 3: Zones**
* Name your 16 zones.
* Select the type for each zone (Motion, Door, Window, Smoke, etc.) from the dropdown.
* *Tip: Leave unused zones empty.*


* **Step 4: Connection**
* **IP Address:** The local IP of your alarm module.
* **Port:** Usually `5002`.



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

```

**Common Errors:**

* `Bootstrap stage 2 timeout`: The integration couldn't connect to the IP during startup. It will keep trying in the background. Check your IP address.
* `500 Internal Server Error`: Ensure you cleared your browser cache (CTRL+F5) after updating the integration.

## Credits

Based on the `pycrowipmodule` library.
Original custom component author: @febalci.
Refactored for Home Assistant 2025+ with Config Flow support.
