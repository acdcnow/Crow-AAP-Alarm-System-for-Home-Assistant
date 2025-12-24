Here is a complete, professional `README.md` file for your GitHub repository. It covers the installation via HACS, configuration, features, and debugging.

---

# Crow/AAP Alarm IP Module for Home Assistant

This is a custom integration for **Home Assistant** to control **Crow Runner**, **AAP (Arrowhead Alarm Products)**, and compatible alarm systems equipped with the **IP Module** (ESIM/TCP) running Firmware Ver 2.10.3628 2017 Oct 20 09:48:43.

Unlike previous solutions, this integration uses a **direct local TCP implementation** (no external Python dependencies like `pycrowipmodule`) to ensure robust connection handling, specific command sequences (`Code` -> `Command` -> `Enter`), and accurate status parsing.

## 🌟 Features

* **Alarm Control Panel:**
* Supports **Arm Away**, **Arm Home (Stay)**, **Disarm**, and **Trigger (Panic)**.
* Supports **Custom Bypass** (via the "Arm Custom Bypass" feature).
* **Keypad Support:** Forces a numeric keypad in the UI to input your user code.
* **Correct Command Sequence:** Automatically handles the required protocol sequence (e.g., `Code` + `ARM` + `Enter`).


* **Binary Sensors (Zones):**
* Supports up to 16 zones.
* Configurable device class (Motion, Door, Window, Smoke, etc.) via the UI.
* Real-time status updates (Open/Closed/Alarm/Tamper).


* **Switches (Outputs):**
* Control up to 2 Relays/Outputs (Output 1 & 2).


* **System Status:**
* Monitors **Mains Power**, **Battery Health**, and **System Tamper**.
* Handles "Power Failure" and "Low Battery" alerts correctly (no false alarms on restart).



---

## 📥 Installation

### Option 1: HACS (Recommended)

This integration is not yet in the default HACS store, so you need to add it as a **Custom Repository**.

1. Open **HACS** in your Home Assistant sidebar.
2. Click on the **Integrations** tab.
3. Click the **three dots** (menu) in the top-right corner.
4. Select **Custom repositories**.
5. In the **Repository** field, paste the URL of this GitHub repository:
```text
https://github.com/YOUR_USERNAME/YOUR_REPO_NAME

```


*(Replace with your actual GitHub repository URL)*
6. In the **Category** dropdown, select **Integration**.
7. Click **Add**.
8. Close the dialog, find the new **Crow/AAP Alarm IP Module** integration in the list, and click **Download**.
9. **Restart Home Assistant**.

### Option 2: Manual Installation

1. Download the `crowipmodule` folder from this repository.
2. Copy the `crowipmodule` folder into your Home Assistant's `custom_components` directory.
* Path: `/config/custom_components/crowipmodule/`


3. **Restart Home Assistant**.

---

## ⚙️ Configuration

This integration uses the Home Assistant **Config Flow** (UI). No YAML configuration is required.

1. Go to **Settings** > **Devices & Services**.
2. Click **+ Add Integration**.
3. Search for **Crow/AAP Alarm IP Module**.
4. Follow the setup wizard steps:

### Step 1: Area Configuration

* **Area 1 / Area 2 Name:** Give your partitions a name (e.g., "House", "Garage").
* **Default Code:** (Optional) If you enter a code here, it will be used as a fallback. However, it is recommended to leave this blank and enter your code via the Lovelace UI Keypad for security.

### Step 2: Relay Configuration

* **Relay 1 / Relay 2 Name:** Name your switchable outputs (e.g., "Garage Door", "Gate"). Leave blank if not used.

### Step 3: Zone Count

* **How many zones do you have?** Enter the total number (1-16).

### Step 4: Zone Details

* The wizard will generate fields based on the count you entered.
* **Name:** e.g., "Kitchen Window".
* **Type:** Select the device class (Motion, Door, Window, Smoke, etc.).

### Step 5: Connection

* **IP Address:** The local IP of your Alarm IP Module.
* **Port:** Usually `5002`.
* **Keep Alive:** Default `60` seconds.
* **Timeout:** Default `10` seconds.

---

## 🎮 Usage

### Alarm Panel Card

Add the standard **Alarm Panel** card to your dashboard.

* **To Arm:**
1. Enter your User Code on the keypad.
2. Press **Arm Away** or **Arm Home**.


* **To Disarm:**
1. Enter your User Code.
2. Press **Disarm**.


* **To Bypass:**
1. Enter your User Code.
2. Press **Bypass** (found under "Arm Custom Bypass" or via service call).



### Switches

Entities will be created for `switch.relay_1` and `switch.relay_2` (if named). These can be used to toggle the PGM outputs on the board (e.g., to open a garage door).

---

## 🛠️ Troubleshooting & Debugging

If you experience connection issues or incorrect status updates, please enable debug logging. This will show the raw communication between Home Assistant and the Alarm Panel.

Add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.crowipmodule: debug

```

**Common Issues:**

* **"Connection Refused":** Ensure no other device (or previous instance of Home Assistant) is connected to the IP Module. The module usually supports only **one** active TCP connection. This is not valid any more 
* **Status not updating:** Ensure your IP Module is configured to send ASCII messages.
* **"Unknown" state on boot:** The integration actively queries the status on connection. If the panel is busy, it might take a few seconds to sync.

---

## 🌐 Supported Languages

The configuration flow is fully translated into:

* 🇬🇧 English
* 🇩🇪 German
* 🇪🇸 Spanish
* 🇮🇹 Italian
* 🇫🇷 French

---

## Credits

Based on the `pycrowipmodule` library.
Original custom component and pypi author: @febalci.
Refactored for Home Assistant 2025+ with Config Flow support.
