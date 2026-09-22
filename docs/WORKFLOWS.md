# Workflows and Diagrams

**Project:** Crow/AAP Alarm IP Module for Home Assistant
**Branch:** `HA2026_09_dev` · **Version:** `2.1.0-beta.1`
**Last updated:** 2026-09-21

Every diagram below is **Mermaid**, so it renders natively on GitHub, in the wiki, and in any
Mermaid-capable viewer. The narrative companion is the [ADD](ADD.md); the module-level detail is the
[SDD](SDD.md).

---

## 1. System context

```mermaid
flowchart LR
    User(["Home owner"])
    HA["Home Assistant<br/>event loop, UI, automations"]
    Int["crowipmodule<br/>custom integration"]
    Driver["pycrowipmodule<br/>vendored driver, socket thread"]

    IPM["Crow IP Module (IA-IP)<br/>serial to Ethernet bridge<br/>firmware 2.10.3628"]
    Panel["Runner 8/16 or AAP ESL-2<br/>areas, zones, outputs"]

    User -->|"dashboard, services"| HA
    HA -->|"entity setup / commands"| Int
    Int --> Driver
    Driver <-->|"TCP 5002, ASCII lines"| IPM
    IPM <-->|"serial bus"| Panel

    classDef local fill:#e8f4f8,stroke:#0b6e8f
    classDef hardware fill:#fdecea,stroke:#b03a3a
    class Int,Driver local
    class IPM,Panel hardware
```

There is no cloud component: everything above happens inside the user's network.

---

## 2. Entry setup workflow

```mermaid
sequenceDiagram
    autonumber
    participant CF as Config Flow
    participant HA as Home Assistant
    participant Init as async_setup_entry
    participant DR as Device Registry
    participant Panel as CrowIPAlarmPanel
    participant Plat as Platforms

    CF->>Panel: socket.create_connection probe
    Panel-->>CF: reachable
    CF->>HA: async_create_entry data + options
    HA->>Init: async_setup_entry entry

    Init->>Panel: CrowIPAlarmPanel host, port, keepalive, timeout
    Init->>Init: entry.runtime_data = CrowRuntimeData controller, firmware
    Init->>Panel: install 6 callbacks
    Init->>DR: async_get_or_create hub device
    DR-->>Init: hub_device.id
    Init->>Init: runtime_data.device_id = hub_device.id
    Note over Init: sleep 2 s - let the panel release a socket from a reload
    Init->>Panel: start in executor
    Panel->>Panel: spawn CrowIPClientThread

    Init->>Plat: async_forward_entry_setups
    Plat->>DR: register entities, device_info with via_device_id
    Init->>HA: async_on_unload stop listener + update listener
    Init-->>HA: True

    Panel-->>HA: callback_connected True
    Note over Panel,HA: call_soon_threadsafe to SIGNAL_CONNECTION_UPDATE
    Panel-->>HA: after 2 s, re-broadcast all state signals with None
```

---

## 3. User command workflow

```mermaid
sequenceDiagram
    autonumber
    participant U as User or automation
    participant E as Entity
    participant P as CrowIPAlarmPanel
    participant C as CrowIPModuleClient
    participant S as Socket

    U->>E: arm_away / disarm / turn_on / press
    E->>P: facade call
    P->>C: send_command key, data
    Note over C: COMMANDS lookup and wire formatting
    C->>S: sendall line + CRLF, under _send_lock

    alt send fails
        C->>C: is_connected = False, close socket
        C-->>P: False
        P->>C: supervisor reconnects with backoff
    else send ok
        S-->>P: panel replies with event lines
        P-->>E: callback, marshalled to the event loop
        E->>E: async_write_ha_state
    end
```

Wire formats produced by the path above:

| Action | Line on the wire |
|---|---|
| Arm away | `ARM ` |
| Arm stay | `STAY ` |
| Disarm with code `1234` | `KEYS 1234E` then `STATUS ` |
| Panic | `PANIC ` |
| Toggle output 2 | `OO2` (no space) |
| Toggle chime | `CHIME ` |
| Relay 1 | `RL1 ` |

---

## 4. Runtime data flow

```mermaid
flowchart TD
    subgraph PanelThread["Panel thread - CrowIPClientThread"]
        RX["socket.recv 1024, timeout 5 s"]
        BUF["line buffer, split on CRLF or LF"]
        PARSE["_parse_line against RESPONSE_FORMATS"]
        HANDLE["handle_*_state_change<br/>mutates panel.x_state"]
        CB["callback_*_state_change payload"]
        RX --> BUF --> PARSE --> HANDLE --> CB
    end

    CB -->|"hass.loop.call_soon_threadsafe"| SEND

    subgraph Loop["Home Assistant event loop"]
        SEND["async_dispatcher_send SIGNAL, payload"]
        Z["CrowZoneSensor"]
        A["CrowAlarmPanel"]
        Y["CrowSystemSensor and status sensors"]
        O["CrowOutput"]
        SEND --> Z
        SEND --> A
        SEND --> Y
        SEND --> O
    end

    Z --> W["async_write_ha_state"]
    A --> W
    Y --> W
    O --> W

    classDef thread fill:#fff4e5,stroke:#b06a00
    classDef loop fill:#e8f5e9,stroke:#2e7d32
    class RX,BUF,PARSE,HANDLE,CB thread
    class SEND,Z,A,Y,O,W loop
```

**Rules.** The panel thread never touches Home Assistant objects. Panel state dicts are written only
by the panel thread and read only by the loop. `None` as a payload means "refresh everything".

---

## 5. Connection lifecycle

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Connecting : start
    Connecting --> Connected : connect ok, backoff reset to 10 s
    Connecting --> Backoff : OSError or timeout
    Connected --> Connected : keep-alive STATUS every keepalive_interval
    Connected --> Disconnected : recv empty or socket error
    Disconnected --> Backoff : notify connection False
    Backoff --> Connecting : wait 10, 20, 40, 60 s cap
    Connected --> Idle : stop
    Backoff --> Idle : stop, wakeup event interrupts the wait
    Disconnected --> Idle : stop
```

Entity availability follows the `SIGNAL_CONNECTION_UPDATE` signal:

```mermaid
flowchart LR
    C1["connected = true"] --> AV["available = true<br/>entities show live state"]
    C2["connected = false"] --> UN["available = false<br/>entities show Unavailable"]
    C1 -->|"socket drops"| C2
    C2 -->|"reconnect ok"| C1
```

---

## 6. Configuration and options flow

**Config flow** (first-time setup, five steps):

```mermaid
stateDiagram-v2
    [*] --> user
    user --> areas : probe reached host and port
    user --> user : cannot_connect
    areas --> outputs
    outputs --> zones : number_of_outputs is 0
    outputs --> zones
    zones --> zones : next 4-zone page
    zones --> [*] : async_create_entry
```

**Options flow** (re-configuration from the integration page):

```mermaid
stateDiagram-v2
    [*] --> init
    init --> areas_opt : pre-filled from entry.options
    areas_opt --> outputs_opt
    outputs_opt --> zones_opt
    zones_opt --> [*] : create entry, then async_reload
```

Zone pages are 4 fields wide (`PAGE_SIZE = 4`), so 16 zones produce four form pages.

---

## 7. Reload and unload

```mermaid
sequenceDiagram
    autonumber
    participant U as User changes options
    participant HA as Home Assistant
    participant UL as update_listener
    participant Un as async_unload_entry

    U->>HA: submit options form
    HA->>UL: options updated
    UL->>HA: async_reload entry_id
    HA->>Un: async_unload_entry
    Un->>HA: async_unload_platforms
    Un->>Un: controller.stop in executor
    Note over Un: sleep 2 s so the single TCP socket is actually released
    Un-->>HA: unload_ok
    HA->>HA: async_setup_entry anew
```

---

## 8. Verification workflow

```mermaid
flowchart LR
    A["compileall<br/>syntax across the integration"]
    B["test_crow_protocol.py<br/>wire formats, RX parsing, loopback"]
    C["tests/verify_ha_2026_contract.py<br/>platforms, DeviceInfo, alarm_state"]
    D["tests/verify_config_flow.py<br/>flow steps, pagination, translations"]
    E["HACS plus live panel<br/>manual smoke test"]

    A --> B --> C --> D --> E
```

Layers A–D run without Home Assistant installed, which is required because Home Assistant 2026.9
needs Python 3.14.2+.

---

## 9. Legacy architecture — GitDiagram reference

[GitDiagram](https://gitdiagram.com) was run against
`acdcnow/Crow-AAP-Alarm-System-for-Home-Assistant`. It reported **16 components and 27 connections**.

> **Important limitation.** GitDiagram analyses the repository's **default branch only**. At the time
> of writing that is `master`, which still depends on the external `pycrowipmodule` package — the tool
> said so itself: *"the external pycrowipmodule implementation was not provided."*
> The diagram therefore describes the **legacy** architecture, not `HA2026_09_dev`.

Re-generate or explore it interactively at:
**https://gitdiagram.com/acdcnow/crow-aap-alarm-system-for-home-assistant**

The equivalent topology, transcribed from GitDiagram's component and edge list:

```mermaid
flowchart TD
    U["Home Assistant User"] -->|configures| CF["Config Flow<br/>config_flow.py"]
    U -->|uses| HA["Home Assistant"]

    CF -->|creates entry| IS["Integration Setup<br/>__init__.py"]
    CF --> AC["Area Configuration"]
    CF --> ZC["Zone Configuration"]
    CF --> OC["Output Configuration"]
    CF --> TR["Translations"]

    IS -->|loads entry| CC["Crow Controller<br/>external pycrowipmodule"]
    IS -->|wires callbacks| SD["Signal Dispatcher"]
    IS -->|forwards setup x5| AP["Alarm Panels"]
    IS -->|forwards setup x5| ZS["Zone Sensors"]
    IS -->|forwards setup x5| OS["Output Switches"]
    IS -->|forwards setup x5| SBS["System Binary Sensors"]
    IS -->|forwards setup x5| STS["Status Text Sensor"]

    CC <-->|maintains TCP| IPM["Crow IP Module"]
    CC -->|sends updates| SD
    SD -->|dispatches area state| AP
    SD -->|dispatches zone state| ZS
    SD -->|dispatches output state| OS
    SD -->|dispatches system state| SBS
    SD -->|dispatches system state| STS

    AP -->|reads area state| CC
    ZS -->|reads zone state| CC
    OS -->|reads output state| CC
    SBS -->|reads system state| CC
    STS -->|reads system state| CC

    AP -->|sends alarm commands| CC
    OS -->|sends output commands| CC

    classDef legacy fill:#f3e5f5,stroke:#6a1b9a
    class CC legacy
```

The same shape in the current (`HA2026_09_dev`) architecture, for comparison — the differences are
the local driver, the extra sensor/button platforms, `runtime_data`, the hub device and diagnostics:

```mermaid
flowchart LR
    CF["Config Flow<br/>5 steps"] --> RD["entry.runtime_data<br/>CrowRuntimeData"]
    RD --> D1["Hub device<br/>crow_alarm_panel"]
    RD --> C["Vendored driver<br/>pycrowipmodule"]
    C <-->|TCP 5002| IPM["Crow IP Module"]
    D1 -.->|via_device_id| D2["Windows / Doors / Sensors<br/>zone sub-devices"]

    RD --> P1["alarm_control_panel"]
    RD --> P2["binary_sensor<br/>zones + 6 statuses"]
    RD --> P3["sensor<br/>status text + last alarm"]
    RD --> P4["switch<br/>outputs"]
    RD --> P5["button<br/>chime + 2 relays"]
    RD --> P6["diagnostics"]
    RD --> P7["brand/<br/>icon + logo"]

    classDef new fill:#e8f5e9,stroke:#2e7d32
    class RD,D1,D2,P5,P6,P7 new
```

Green nodes mark what the 2026.9 development branch added or changed.

---

## 10. Release workflow

```mermaid
flowchart LR
    Dev["Commit to<br/>HA2026_09_dev"] --> Ver{"All four<br/>checks pass"}
    Ver -->|no| Dev
    Ver -->|yes| Bump["Bump manifest version<br/>and CHANGELOG"]
    Bump --> Tag["Annotated tag<br/>no v prefix"]
    Tag --> Push["Push branch and tag"]
    Push --> Rel["GitHub pre-release<br/>with release notes"]
    Rel --> HACS["HACS offers it<br/>when betas are enabled"]
    Rel --> PR["PR stays open<br/>until promotion to stable"]
```
