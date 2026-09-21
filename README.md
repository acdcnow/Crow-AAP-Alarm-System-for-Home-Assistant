<p align="center">
  <img src="custom_components/crowipmodule/brand/logo.png" alt="Crow/AAP Alarm IP Module" width="420">
</p>

# Crow/AAP Alarm IP Module for Home Assistant

This is a custom integration for **Home Assistant** to control **Crow Runner**, **AAP (Arrowhead Alarm Products)**, and compatible alarm systems equipped with the **IP Module** (ESIM/TCP) running Firmware Ver 2.10.3628 2017 Oct 20 09:48:43.

Unlike previous solutions, this integration uses a **direct local TCP implementation** (the driver is vendored inside the integration, so no external Python dependency is installed) to ensure robust connection handling, specific command sequences (`Code` -> `Command` -> `Enter`), and accurate status parsing.

> **Current release: `2.1.0-beta.1` (pre-release).** Targets Home Assistant 2026.9.3.
> HACS only offers this if you enable *Show beta versions* on the integration page.
> Users on Home Assistant 2026.8 or older should stay on `2.0.0`.

## ✅ Requirements

* **Home Assistant 2026.9.3 or newer** (Home Assistant 2026.9 requires Python 3.14.2+).
* A Crow Runner 8/16 or AAP ESL-2 board with the IP Module / APP POD.
* The panel must speak the ASCII line protocol on TCP port `5002` (the default).

## 📚 Documentation

**Design documents (in this repository)**

| Document | What it covers |
|---|---|
| [Architectural Design Document](docs/ADD.md) | Context, architectural decisions, runtime view, quality attributes, risks |
| [Software Design Document](docs/SDD.md) | Modules, signatures, data models, protocol tables, per-entity contracts |
| [Workflows and Diagrams](docs/WORKFLOWS.md) | Mermaid diagrams: setup, data flow, commands, connection lifecycle, release |

**Wiki**

| Page | Audience |
|---|---|
| [Home / landing page](https://github.com/acdcnow/Crow-AAP-Alarm-System-for-Home-Assistant/wiki) | Everyone - picks the right track for your version |
| [HA 2026.09 Development Branch](https://github.com/acdcnow/Crow-AAP-Alarm-System-for-Home-Assistant/wiki/HA-2026.09-Development-Branch) | Users of the `2.1.0-beta.1` pre-release |
| [Archived Documentation](https://github.com/acdcnow/Crow-AAP-Alarm-System-for-Home-Assistant/wiki/Archived-Documentation) | Users still on 1.x / 2.0.0 |

**Interactive architecture map** - [GitDiagram](https://gitdiagram.com/acdcnow/crow-aap-alarm-system-for-home-assistant) renders the repository as a component graph. Note that it reads the **default branch** only, so it currently shows the legacy `master` architecture.

## 🌟 Features

* **Alarm Control Panel:**
* Supports **Arm Away**, **Arm Home (Stay)**, **Disarm**, and **Trigger (Panic)**.
* Supports **Custom Bypass** (via the "Arm Custom Bypass" feature).
* **Keypad Support:** Forces a numeric keypad in the UI to input your user code.
* **Correct Command Sequence:** Automatically handles the required protocol sequence (e.g., `Code` + `ARM` + `Enter`).
* Entities become **unavailable** when the TCP connection drops, instead of silently showing stale state.


* **Binary Sensors (Zones):**
* Supports up to 16 zones.
* Configurable device class (Motion, Door, Window, Smoke, etc.) via the UI.
* Real-time status updates (Open/Closed/Alarm/Tamper).
* Zones are grouped into sub-devices (Windows / Doors / Sensors) linked to the main panel.


* **Switches (Outputs):**
* Control up to 8 board outputs.


* **Buttons:**
* **Toggle Chime**, plus **Relay 1** / **Relay 2** momentary activation.


* **System Status:**
* Monitors **Mains Power**, **Battery Health**, **Tamper**, **Phone Line**, **Dialler** and **Zone Battery**.
* Handles "Power Failure" and "Low Battery" alerts correctly (no false alarms on restart).


* **Device page:** the panel reports its firmware version, the configured host and links to `http://<host>`.
* **Diagnostics:** downloadable from the integration page with area codes and the host redacted.



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
* **Arm Sequence:** How the panel expects to be armed. Leave the default unless arming does
  nothing - see [Arming Sequence](#arming-sequence).

---

## 🎮 Usage

### Alarm Panel Card

Add the standard **Alarm Panel** card to your dashboard.

* **To Arm:** Press **Arm Away** or **Arm Home**. If no code is stored for the area, Home
  Assistant asks for one first; otherwise the stored code is sent automatically.
* **To Disarm:** Press **Disarm** and enter your user code (again, unless a code is stored
  for the area).
* **To Trigger:** Press **Trigger** to raise a panic alarm (`PANIC`).

* **To Bypass:**
1. Enter your User Code.
2. Press **Bypass** (found under "Arm Custom Bypass" or via service call).



### Arming Sequence

The Crow protocol has no single "arm with code" command. Depending on the firmware and how
the panel is programmed, either

* the bare `ARM` / `STAY` command completes the arming, or
* the panel sends `ARM` / `STAY` and then **waits for the user code followed by Enter**.

Select the matching behaviour with the **Arm Sequence** option, under
**Settings > Devices & Services > Crow/AAP Alarm IP Module > Configure** (it is also the last
step of the setup wizard).

| Option | Arm Away sends | Arm Home sends | Use when |
| --- | --- | --- | --- |
| **Command, then code + Enter** (default) | `ARM ` then `KEYS <code>E` | `STAY ` then `KEYS <code>E` | The panel waits for your code before it arms. This matches the behaviour of `2.0.0`. |
| **Command only** | `ARM ` | `STAY ` | The panel arms immediately on the command, and a following code press would cancel the arming. |

The trailing `E` in `KEYS <code>E` is the **Enter** key, so the sequence above is the keypad
equivalent of typing your code and pressing Enter. No separate Enter button is required.

**Disarming** is always keypad style - the code followed by Enter (`KEYS <code>E`, then
`STATUS `) - regardless of the selected arm sequence.

> [!NOTE]
> If **Command, then code + Enter** is selected but the area has no code stored, only the arm
> command is sent and a warning is written to the log. Store the area code, or switch to
> **Command only**.

### Switches

Entities will be created for `switch.relay_1` and `switch.relay_2` (if named). These can be used to toggle the PGM outputs on the board (e.g., to open a garage door).

Outputs are **momentary** on the Crow protocol: turning a switch on sends the `OO<n>` command, so the board toggles its output. Two consecutive toggles within one status refresh are debounced to avoid double-triggering.

### Buttons

* **Toggle Chime** - toggles the panel's keypad chime.
* **Relay 1** / **Relay 2** - briefly energise the board relays (`RL1` / `RL2`).

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

* **"Connection Refused":** Ensure no other device (or previous instance of Home Assistant) is connected to the IP Module. Older firmware only tolerated **one** active TCP connection at a time; newer firmware allows reconnects while an old socket is still winding down, and the integration retries with exponential backoff.
* **Status not updating:** Ensure your IP Module is configured to send ASCII messages.
* **"Unknown" state on boot:** The integration actively queries the status on connection. If the panel is busy, it might take a few seconds to sync.
* **Arming does nothing:** The panel is waiting for your user code. Set **Arm Sequence** to
  **Command, then code + Enter** and make sure the area has a code stored - see
  [Arming Sequence](#arming-sequence).
* **The panel disarms instead of arming:** Set **Arm Sequence** to **Command only**. On these
  panels the code press that follows the arm command is read as a disarm.

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

Based on the `pycrowipmodule` library by @febalci, which the driver inside
`custom_components/crowipmodule/pycrowipmodule/` is derived from (MIT).
Original custom component and pypi author: @febalci.
Refactored for Home Assistant 2026.9+ with Config Flow support, `entry.runtime_data`
and a `brand/` asset directory.
