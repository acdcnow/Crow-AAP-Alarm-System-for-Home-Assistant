/* =============================================================================
   Alarmanlage - dashboard preview
   -----------------------------------------------------------------------------
   Renders the exact card tree of ../alarm-dashboard.yaml (converted to JSON by
   build_cards.py, so there is no second copy of the cards that could drift)
   with a fake `hass` object, Home Assistant's real design tokens and its real
   card semantics.

   What is faithful:
     * the card tree, names, icons, colours, column spans and features
     * visibility rules - both on cards and on whole sections, including
       nested and/or conditions
     * the colour logic of the tile card: `color` is the colour while ACTIVE,
       inactive is the inactive colour; a tile without `color` falls back to
       stateColorCss(), which is why an open door would be amber and not red
     * the `alarm-modes` feature: only modes the entity reports, and a single
       Disarm button while the panel is arming or triggered
     * the Jinja in the markdown cards, evaluated against the simulated states
       (a small Jinja subset: `{% if %}`, `{% set %}`, `{{ }}`, expand(),
       is_state(), state_attr() and the filters selectattr/map/join/length)
     * relative times, and the pulse animation on alarm tiles

   What is approximated:
     * the cards themselves (tile, heading, logbook, history-graph, alarm-panel)
       are hand built stand-ins with the HA look
     * the logbook entries and the 24 h history are generated, not recorded
     * state labels that Home Assistant has no translation for
       (e.g. binary_sensor with device_class tamper)
   ========================================================================== */
(() => {
  "use strict";

  const MDI = window.MDI || {};
  const FALLBACK_ICON = "M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4Z";

  const ALARM = "alarm_control_panel.security_crow_alarm_system_a";
  const EXPERT = "input_boolean.expert_mode";
  const ALL_CLOSED = "binary_sensor.alles_geschlossen";

  const ZONES_PERIMETER = [
    "binary_sensor.crow_alarm_doors_eingangstur",
    "binary_sensor.crow_alarm_doors_terrassentur",
    "binary_sensor.crow_alarm_windows_wohnzimmer_fenster",
    "binary_sensor.crow_alarm_system_kuche_fenster",
    "binary_sensor.crow_alarm_windows_gastewc_fenster",
    "binary_sensor.crow_alarm_windows_schlaf_bad_fenster",
    "binary_sensor.crow_alarm_windows_kinder_fenster",
  ];

  /* ==========================================================================
     1. Simulated entities
     --------------------------------------------------------------------------
     [state, { n: friendly name, icon, dc: device class, lc: seconds since the
               state changed, a: extra attributes }]
     ========================================================================== */
  const BASE = {
    [ALARM]: ["disarmed", { n: "Haus Alarmsystem", icon: "shield-home", lc: 5400, a: {
      code_format: "number", code_arm_required: false, alarm_zone: "",
      last_armed_by_user: "3", last_disarmed_by_user: "3", changed_by: null,
    } }],
    [ALL_CLOSED]: ["on", { n: "Alles geschlossen", icon: "shield-check", lc: 5400 }],
    [EXPERT]: ["off", { n: "Alarm Expertenmodus", icon: "account-hard-hat", lc: 43200 }],
    "sensor.crow_system_status": ["Ready", { n: "System Status", icon: "shield-home", lc: 5400 }],

    /* --- Türen --- */
    "binary_sensor.crow_alarm_doors_eingangstur": ["off", { n: "Eingangstür", icon: "door", dc: "door", lc: 5400 }],
    "binary_sensor.crow_alarm_doors_terrassentur": ["off", { n: "Terrassentür", icon: "door-sliding", dc: "door", lc: 6100 }],

    /* --- Fenster --- */
    "binary_sensor.crow_alarm_windows_wohnzimmer_fenster": ["off", { n: "Wohnzimmer", icon: "window-closed", dc: "window", lc: 7400 }],
    "binary_sensor.crow_alarm_system_kuche_fenster": ["off", { n: "Küche", icon: "window-closed", dc: "window", lc: 7300 }],
    "binary_sensor.crow_alarm_windows_gastewc_fenster": ["off", { n: "Gäste-WC", icon: "window-closed", dc: "window", lc: 8100 }],
    "binary_sensor.crow_alarm_windows_schlaf_bad_fenster": ["off", { n: "Schlaf/Bad OG", icon: "window-closed", dc: "window", lc: 6100 }],
    "binary_sensor.crow_alarm_windows_kinder_fenster": ["off", { n: "Kinder OG", icon: "window-closed", dc: "window", lc: 6500 }],

    /* --- Bewegung --- */
    "binary_sensor.bewegungsmelder_vorzimmer": ["off", { n: "Bewegungsmelder Vorzimmer", icon: "motion-sensor", dc: "motion", lc: 700 }],
    "binary_sensor.bewegungsmelder_keller_1": ["off", { n: "Bewegungsmelder Keller 1", icon: "motion-sensor", dc: "motion", lc: 1500 }],
    "binary_sensor.bewegungsmelder_keller_2": ["off", { n: "Bewegungsmelder Keller 2", icon: "motion-sensor", dc: "motion", lc: 2600 }],
    "binary_sensor.bewegungsmelder_gastewc": ["off", { n: "Bewegungsmelder Gäste-WC", icon: "motion-sensor", dc: "motion", lc: 3100 }],
    "binary_sensor.bewegungsmelder_wc": ["off", { n: "Bewegungsmelder WC", icon: "motion-sensor", dc: "motion", lc: 1900 }],
    "binary_sensor.bewegungsmelder_technikraum": ["off", { n: "Bewegungsmelder Technikraum", icon: "motion-sensor", dc: "motion", lc: 4200 }],
    "binary_sensor.bewegungsmelder_wascheabwurfraum": ["off", { n: "Bewegungsmelder Wäscheabwurf", icon: "motion-sensor", dc: "motion", lc: 5200 }],
    "binary_sensor.bewegungsmelder_lagerraum": ["off", { n: "Bewegungsmelder Lagerraum", icon: "motion-sensor", dc: "motion", lc: 3900 }],

    /* --- System (Polarität wie in binary_sensor.py) --- */
    "binary_sensor.crow_alarm_system_mains_power": ["on", { n: "Mains Power", icon: "power-plug", dc: "power", lc: 86400 }],
    "binary_sensor.crow_alarm_system_system_battery": ["off", { n: "System Battery", icon: "battery-check-outline", dc: "battery", lc: 86400 }],
    "binary_sensor.crow_alarm_system_zone_battery": ["off", { n: "Zone Battery", icon: "battery-check-outline", dc: "battery", lc: 86400 }],
    "binary_sensor.crow_alarm_system_system_tamper": ["off", { n: "System Tamper", icon: "alert-decagram", dc: "tamper", lc: 86400 }],
    "binary_sensor.crow_alarm_system_phone_line": ["on", { n: "Phone Line", icon: "phone", dc: "connectivity", lc: 86400 }],
    "binary_sensor.crow_alarm_system_dialler": ["on", { n: "Dialler", icon: "phone-outgoing", dc: "connectivity", lc: 86400 }],
  };

  /* `patch` entries are [state, seconds-since-change] applied on top of BASE. */
  const SCENARIOS = {
    quiet: { label: "Ruhig", patch: {} },
    armed: { label: "Scharf", patch: {
      [ALARM]: ["armed_away", { lc: 7200, a: { last_armed_by_user: "3" } }],
    } },
    open: { label: "Zonen offen", patch: {
      "binary_sensor.crow_alarm_doors_eingangstur": ["on", { lc: 240 }],
      "binary_sensor.crow_alarm_system_kuche_fenster": ["on", { lc: 900 }],
      "binary_sensor.bewegungsmelder_vorzimmer": ["on", { lc: 12 }],
    } },
    alarm: { label: "Alarm", patch: {
      [ALARM]: ["triggered", { lc: 95, a: { alarm_zone: "3" } }],
      "binary_sensor.crow_alarm_doors_terrassentur": ["on", { lc: 95 }],
      "binary_sensor.bewegungsmelder_vorzimmer": ["on", { lc: 40 }],
    } },
    fault: { label: "Störung", patch: {
      "binary_sensor.crow_alarm_system_mains_power": ["off", { lc: 1800 }],
      "binary_sensor.crow_alarm_system_system_battery": ["on", { lc: 1800 }],
      "binary_sensor.crow_alarm_system_system_tamper": ["on", { lc: 900 }],
    } },
  };

  /* ==========================================================================
     2. Formatting helpers
     ========================================================================== */
  const esc = (s) =>
    String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  const iconPath = (name) => MDI[String(name || "").replace(/^mdi:/, "")] || FALLBACK_ICON;

  const svgIcon = (name, cls = "") =>
    `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path d="${iconPath(name)}"></path></svg>`;

  function relativeTime(seconds) {
    if (seconds === null || seconds === undefined) return "";
    const s = Math.max(0, Math.round(seconds));
    if (s < 45) return "gerade eben";
    if (s < 3600) return `vor ${Math.round(s / 60)} Min.`;
    if (s < 86400) {
      const h = Math.round(s / 3600);
      return `vor ${h} Std.`;
    }
    const d = Math.round(s / 86400);
    return `vor ${d} Tag${d === 1 ? "" : "en"}`;
  }

  function clockTime(seconds) {
    const d = new Date(Date.now() - seconds * 1000);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }

  /* Translations the preview needs. Only the states that actually occur. */
  const BINARY_STATES = {
    door: { on: "Offen", off: "Geschlossen" },
    window: { on: "Offen", off: "Geschlossen" },
    opening: { on: "Offen", off: "Geschlossen" },
    garage_door: { on: "Offen", off: "Geschlossen" },
    motion: { on: "Erkannt", off: "Frei" },
    problem: { on: "Problem", off: "OK" },
    safety: { on: "Problem", off: "OK" },
    battery: { on: "Schwach", off: "OK" },
    power: { on: "An", off: "Aus" },
    connectivity: { on: "Verbunden", off: "Getrennt" },
    // Home Assistant has no device-class translation for tamper; it shows on/off.
    tamper: { on: "Ausgelöst", off: "OK" },
  };

  const ALARM_STATES = {
    disarmed: "Unscharf",
    armed_home: "Scharf (zu Hause)",
    armed_away: "Scharf (abwesend)",
    arming: "Scharfschaltung läuft",
    pending: "Ausgangsverzögerung",
    triggered: "Ausgelöst",
    unavailable: "Nicht verfügbar",
  };

  /* ==========================================================================
     3. The simulated `hass`
     ========================================================================== */
  let S = {};
  let scenarioKey = "quiet";

  function buildStates() {
    const scenario = SCENARIOS[scenarioKey];
    S = {};
    for (const [id, [state, meta]] of Object.entries(BASE)) {
      S[id] = {
        entity_id: id,
        state,
        attributes: Object.assign({ friendly_name: meta.n, icon: `mdi:${meta.icon}`, device_class: meta.dc }, meta.a || {}),
        _changed: meta.lc,
      };
    }
    for (const [id, [state, meta]] of Object.entries(scenario.patch)) {
      S[id] = {
        entity_id: id,
        state,
        attributes: Object.assign(
          { friendly_name: BASE[id][1].n, icon: BASE[id][1].icon ? `mdi:${BASE[id][1].icon}` : undefined, device_class: BASE[id][1].dc },
          meta.a || {}
        ),
        _changed: meta.lc,
      };
    }
    // `alles geschlossen` and the panel's own status text follow the zones,
    // exactly like the integration derives them.
    const openPerimeter = ZONES_PERIMETER.filter((z) => S[z].state === "on");
    S[ALL_CLOSED] = Object.assign({}, S[ALL_CLOSED], {
      state: openPerimeter.length ? "off" : "on",
      _changed: openPerimeter.length ? Math.min(...openPerimeter.map((z) => S[z]._changed)) : 5400,
    });

    const status = S["sensor.crow_system_status"];
    const st = S[ALARM].state;
    const a = S[ALARM].attributes;
    let text = "Ready";
    if (st === "triggered") text = "ALARM";
    else if (st === "armed_away") text = "Armed Away";
    else if (st === "armed_home") text = "Armed Stay";
    else if (st === "arming") text = "Exit Delay";
    else if (S["binary_sensor.crow_alarm_system_mains_power"].state === "off") text = "Power Failure";
    else if (S["binary_sensor.crow_alarm_system_system_battery"].state === "on") text = "Low Battery";
    status.state = text;
    status._changed = st === "disarmed" ? 5400 : S[ALARM]._changed;
    void a;
  }

  const hass = {
    language: "de",
    states: {},
    formatEntityName(stateObj, override) {
      if (override) return override;
      return stateObj.attributes.friendly_name || stateObj.entity_id;
    },
    formatEntityState(stateObj) {
      const id = stateObj.entity_id;
      const s = stateObj.state;
      if (id.startsWith("alarm_control_panel.")) return ALARM_STATES[s] || s;
      if (id.startsWith("binary_sensor.")) {
        const table = BINARY_STATES[stateObj.attributes.device_class];
        if (table && table[s]) return table[s];
        return s === "on" ? "Ein" : s === "off" ? "Aus" : s;
      }
      return s;
    },
  };

  /* ==========================================================================
     4. A very small Jinja subset
     --------------------------------------------------------------------------
     Supports what the markdown cards in alarm-dashboard.yaml use:
       {% if EXPR %} {% else %} {% endif %}   {% set NAME = EXPR %}
       {{ EXPR }}   with expand(), is_state(), state_attr(), states() and the
       filters selectattr / map / join / length / list / int / count / first
     ========================================================================== */
  const FILTERS = {
    selectattr: (list, attr, test, value) => {
      if (test === undefined) return list.filter((x) => truthy(attrOf(x, attr)));
      if (test === "eq") return list.filter((x) => attrOf(x, attr) === value);
      if (test === "ne") return list.filter((x) => attrOf(x, attr) !== value);
      throw new Error(`selectattr test '${test}' is not supported by the preview`);
    },
    map: (list, opts) => {
      const attr = typeof opts === "string" ? opts : opts && opts.attribute;
      return list.map((x) => attrOf(x, attr));
    },
    join: (list, sep = "") => list.join(sep === undefined ? "" : sep),
    length: (x) => (x == null ? 0 : x.length),
    count: (x) => (x == null ? 0 : x.length),
    list: (x) => Array.from(x),
    first: (x) => x[0],
    int: (x, fallback = 0) => (Number.isFinite(parseInt(x, 10)) ? parseInt(x, 10) : fallback),
    float: (x, fallback = 0) => (Number.isFinite(parseFloat(x)) ? parseFloat(x) : fallback),
    trim: (x) => String(x).trim(),
  };

  const FUNCS = {
    expand: (...ids) => {
      const flat = ids.flat().flatMap((v) => (typeof v === "string" ? v.split(",") : [])).map((s) => s.trim()).filter(Boolean);
      return flat.map((id) => S[id]).filter(Boolean);
    },
    is_state: (id, want) => !!S[id] && S[id].state === want,
    states: (id) => (S[id] ? S[id].state : "unknown"),
    state_attr: (id, attr) => {
      if (!S[id]) return null;
      const v = S[id].attributes[attr];
      return v === undefined ? null : v;
    },
  };

  function attrOf(obj, attr) {
    if (obj == null || attr == null) return undefined;
    if (attr === "state") return obj.state;
    if (attr === "name") return obj.attributes.friendly_name;
    if (attr === "last_changed") return obj._changed;
    return obj.attributes[attr];
  }

  const truthy = (v) => (Array.isArray(v) ? v.length > 0 : Boolean(v));

  const ARG_NAMES = [...Object.keys(FILTERS), ...Object.keys(FUNCS)];
  const COMPILED = new Map();

  function compileJs(js, argNames) {
    const key = `${argNames.join(",")}\u0001${js}`;
    if (!COMPILED.has(key)) {
      // eslint-disable-next-line no-new-func
      COMPILED.set(key, new Function(...argNames, `"use strict"; return (${js});`));
    }
    return COMPILED.get(key);
  }

  function splitTop(expr, sep) {
    const parts = [];
    let depth = 0;
    let current = "";
    for (const ch of expr) {
      if (ch === "(" || ch === "[") depth++;
      else if (ch === ")" || ch === "]") depth--;
      if (ch === sep && depth === 0) {
        parts.push(current);
        current = "";
      } else {
        current += ch;
      }
    }
    parts.push(current);
    return parts;
  }

  function evalExpr(source, scope) {
    const strings = [];
    let expr = String(source).replace(/'([^']*)'|"([^"]*)"/g, (_m, a, b) => {
      strings.push(a !== undefined ? a : b);
      return `\u0000${strings.length - 1}\u0000`;
    });

    if (expr.includes("|")) {
      const segments = splitTop(expr, "|");
      let acc = segments[0].trim();
      for (let i = 1; i < segments.length; i++) {
        const seg = segments[i].trim();
        const m = /^([A-Za-z_]\w*)\s*(?:\(([\s\S]*)\))?$/.exec(seg);
        if (!m) throw new Error(`unsupported filter expression: ${seg}`);
        acc = m[2] !== undefined ? `${m[1]}(${acc}, ${m[2]})` : `${m[1]}(${acc})`;
      }
      expr = acc;
    }

    expr = expr
      .replace(/\band\b/g, "&&")
      .replace(/\bor\b/g, "||")
      .replace(/\bnot\b/g, "!")
      .replace(/\bTrue\b/g, "true")
      .replace(/\bFalse\b/g, "false")
      .replace(/\bNone\b/g, "null")
      // `map(attribute='name')` is the only keyword argument in these
      // templates; JS has no keyword arguments, so it becomes positional.
      .replace(/\battribute\s*=\s*/g, "")
      .replace(/\u0000(\d+)\u0000/g, (_m, i) => JSON.stringify(strings[Number(i)]));

    // Template variables from {% set %} become parameters of the compiled
    // function - without this a later {{ zonen }} could not see them.
    const extra = Object.keys(scope || {}).filter((k) => /^[A-Za-z_]\w*$/.test(k) && !ARG_NAMES.includes(k));
    const argNames = [...ARG_NAMES, ...extra];
    const values = argNames.map((n) => (scope && n in scope ? scope[n] : FILTERS[n] || FUNCS[n]));
    return compileJs(expr, argNames)(...values);
  }

  function renderTemplate(template, extraScope) {
    const scope = Object.assign({}, extraScope);
    const re = /\{%\s*([\s\S]*?)\s*%\}|\{\{\s*([\s\S]*?)\s*\}\}/g;
    const stack = [];
    let active = true;
    let out = "";
    let cursor = 0;
    let m;

    while ((m = re.exec(template)) !== null) {
      const text = template.slice(cursor, m.index);
      if (active) out += text;
      cursor = re.lastIndex;

      if (m[2] !== undefined) {
        if (active) {
          const value = evalExpr(m[2], scope);
          out += value === null || value === undefined ? "" : String(value);
        }
        continue;
      }

      const stmt = m[1];
      if (/^if\s/.test(stmt)) {
        const parent = active;
        const taken = parent && truthy(evalExpr(stmt.replace(/^if\s+/, ""), scope));
        active = taken;
        stack.push({ parent, taken, inElse: false });
      } else if (/^else\s*$/.test(stmt) || /^elif\s/.test(stmt)) {
        const frame = stack[stack.length - 1];
        if (frame.inElse) throw new Error("a second {% else %} in one {% if %}");
        frame.inElse = true;
        active = frame.parent && !frame.taken;
        frame.taken = frame.taken || active;
      } else if (/^endif\s*$/.test(stmt)) {
        const frame = stack.pop();
        if (!frame) throw new Error("{% endif %} without {% if %}");
        active = frame.parent;
      } else if (/^set\s/.test(stmt)) {
        if (active) {
          const set = /^set\s+([A-Za-z_]\w*)\s*=\s*([\s\S]*)$/.exec(stmt);
          if (!set) throw new Error(`unsupported {% set %}: ${stmt}`);
          scope[set[1]] = evalExpr(set[2], scope);
        }
      } else if (active) {
        throw new Error(`the preview does not implement {% ${stmt} %}`);
      }
    }
    if (stack.length) throw new Error("unclosed {% if %}");
    out += active ? template.slice(cursor) : "";
    return out;
  }

  /* ==========================================================================
     5. Conditions (the conditional card and card/section visibility)
     ========================================================================== */
  function conditionOk(condition) {
    if (!condition) return true;
    switch (condition.condition) {
      case "state": {
        const st = S[condition.entity];
        if (!st) return false;
        if (condition.state_not !== undefined) {
          const not = [].concat(condition.state_not);
          return !not.includes(st.state);
        }
        return [].concat(condition.state).includes(st.state);
      }
      case "numeric_state": {
        const st = S[condition.entity];
        if (!st) return false;
        const n = parseFloat(st.state);
        if (!Number.isFinite(n)) return false;
        if (condition.above !== undefined && !(n > parseFloat(condition.above))) return false;
        if (condition.below !== undefined && !(n < parseFloat(condition.below))) return false;
        return true;
      }
      case "and": return (condition.conditions || []).every(conditionOk);
      case "or": return (condition.conditions || []).some(conditionOk);
      case "not": return !(condition.conditions || []).some(conditionOk);
      default:
        return true;
    }
  }

  function visible(item) {
    const conditions = item && item.visibility;
    if (!conditions || !conditions.length) return true;
    return conditions.every(conditionOk);
  }

  /* ==========================================================================
     6. Colour logic (tile card)
     ========================================================================== */
  const COLOR_TOKENS = {
    primary: "var(--primary-color)", accent: "var(--accent-color)", disabled: "var(--disabled-text-color)",
    red: "var(--red-color)", pink: "var(--pink-color)", purple: "var(--purple-color)",
    "deep-purple": "var(--deep-purple-color)", indigo: "var(--indigo-color)", blue: "var(--blue-color)",
    "light-blue": "var(--light-blue-color)", cyan: "var(--cyan-color)", teal: "var(--teal-color)",
    green: "var(--green-color)", "light-green": "var(--light-green-color)", lime: "var(--lime-color)",
    yellow: "var(--yellow-color)", amber: "var(--amber-color)", orange: "var(--orange-color)",
    "deep-orange": "var(--deep-orange-color)", brown: "var(--brown-color)", grey: "var(--grey-color)",
    "blue-grey": "var(--blue-grey-color)", black: "var(--black-color)", white: "var(--white-color)",
  };

  function cssColor(token) {
    if (!token) return undefined;
    if (token.startsWith("#") || token.startsWith("var(") || token.startsWith("rgb")) return token;
    return COLOR_TOKENS[token] || token;
  }

  /* stateActive() from common/entity/state_active.ts */
  function stateActive(stateObj) {
    const state = stateObj.state;
    const domain = stateObj.entity_id.split(".")[0];
    if (state === "unavailable" || state === "unknown") return false;
    if (state === "off" && domain !== "alert") return false;
    switch (domain) {
      case "alarm_control_panel": return state !== "disarmed";
      case "cover": return state !== "closed";
      case "device_tracker":
      case "person": return state !== "not_home";
      case "lock": return state !== "locked";
      case "media_player": return state !== "standby";
      default: return true;
    }
  }

  /* stateColorCss() from common/entity/state_color.ts - only for the domains
     that carry a state colour; everything else falls back to the tile default. */
  const COLORED_DOMAINS = new Set([
    "alarm_control_panel", "alert", "automation", "binary_sensor", "calendar", "camera",
    "climate", "cover", "device_tracker", "fan", "group", "humidifier", "input_boolean",
    "lawn_mower", "light", "lock", "media_player", "person", "plant", "remote", "schedule",
    "script", "siren", "sun", "switch", "timer", "update", "vacuum", "valve", "water_heater",
    "weather",
  ]);

  const STATE_COLORS = {
    "alarm_control_panel": {
      armed_away: "var(--green-color)", armed_home: "var(--green-color)", armed_night: "var(--green-color)",
      armed_vacation: "var(--green-color)", armed_custom_bypass: "var(--green-color)",
      arming: "var(--orange-color)", pending: "var(--orange-color)", disarming: "var(--orange-color)",
      triggered: "var(--red-color)",
    },
    "binary_sensor": {
      "battery:on": "var(--red-color)", "carbon_monoxide:on": "var(--red-color)",
      "gas:on": "var(--red-color)", "heat:on": "var(--red-color)", "lock:on": "var(--red-color)",
      "moisture:on": "var(--red-color)", "problem:on": "var(--red-color)",
      "safety:on": "var(--red-color)", "smoke:on": "var(--red-color)",
      "sound:on": "var(--red-color)", "tamper:on": "var(--red-color)",
    },
  };

  function stateColorCss(stateObj) {
    if (stateObj.state === "unavailable") return "var(--state-inactive-color)";
    const domain = stateObj.entity_id.split(".")[0];
    if (!COLORED_DOMAINS.has(domain)) return undefined;
    const table = STATE_COLORS[domain];
    if (table) {
      const dc = stateObj.attributes.device_class;
      if (dc && table[`${dc}:${stateObj.state}`]) return table[`${dc}:${stateObj.state}`];
      if (table[stateObj.state]) return table[stateObj.state];
    }
    // domain default: active colour when active, inactive colour when not
    return stateActive(stateObj) ? "var(--state-binary_sensor-active-color, var(--amber-color))" : "var(--state-inactive-color)";
  }

  function tileColor(stateObj, configured) {
    if (configured) return stateActive(stateObj) ? cssColor(configured) : undefined;
    if (stateObj.entity_id.startsWith("person.") || stateObj.entity_id.startsWith("device_tracker.")) return undefined;
    return stateColorCss(stateObj);
  }

  /* ==========================================================================
     7. Cards
     ========================================================================== */
  const card = (html, extra = "") => `<div class="ha-card ${extra}">${html}</div>`;

  function renderBadge(badge) {
    if (!visible(badge)) return "";
    if (badge.type === "button") {
      const color = badge.color ? ` style="color:${cssColor(badge.color)}"` : "";
      return `<span class="h-badge button-badge pill"${color}>${badge.icon ? svgIcon(badge.icon) : ""}${badge.text ? esc(badge.text) : ""}</span>`;
    }
    const st = S[badge.entity];
    if (!st) return `<span class="h-badge">${esc(badge.entity)} (unbekannt)</span>`;
    const color = badge.color ? cssColor(badge.color) : undefined;
    const parts = [];
    if (badge.icon) parts.push(svgIcon(badge.icon));
    if (badge.show_name) parts.push(`<span class="badge-name-inline">${esc(hass.formatEntityName(st, badge.name))}</span>`);
    const showState = badge.show_state !== false;
    if (showState) parts.push(`<span class="badge-state-inline">${esc(hass.formatEntityState(st))}</span>`);
    const style = color ? ` style="color:${color}"` : "";
    return `<span class="h-badge"${style}>${parts.join("")}</span>`;
  }

  function headingBadges(badges) {
    const html = (badges || []).map(renderBadge).join("");
    return html ? `<div class="heading-badges">${html}</div>` : "";
  }

  function renderHeading(c) {
    const style = c.heading_style === "subtitle" ? "heading-title subtitle" : "heading-title";
    return `<div class="local-card heading-card">
      <div class="heading-row">
        <div class="${style}">${c.icon ? svgIcon(c.icon) : ""}<p>${esc(c.heading || "")}</p></div>
        ${headingBadges(c.badges)}
      </div>
    </div>`;
  }

  function renderAlarmModesFeature(feature, stateObj) {
    const supported = ["armed_home", "armed_away", "disarmed"]; // what crowipmodule reports
    const wanted = feature.modes ? supported.filter((m) => feature.modes.includes(m)) : supported;
    const options = wanted.slice().reverse(); // the feature reverses the list
    const color = stateColorCss(stateObj) || "var(--state-icon-color)";

    if (["triggered", "arming", "pending"].includes(stateObj.state)) {
      return `<div class="feature alarm-modes"><div class="mode-select">
        <span class="mode-option disarm">${svgIcon("shield-off")} Disarm</span>
      </div></div>`;
    }

    const MODE_ICONS = { armed_home: "home", armed_away: "lock", disarmed: "shield-off" };
    const MODE_LABELS = { armed_home: "Zuhause", armed_away: "Abwesend", disarmed: "Unscharf" };
    const rendered = options
      .map((mode) => {
        const active = stateObj.state === mode ? " active" : "";
        return `<span class="mode-option${active}" title="${MODE_LABELS[mode]}">${svgIcon(mode === "disarmed" ? "shield-off" : MODE_ICONS[mode])}</span>`;
      })
      .join("");
    return `<div class="feature alarm-modes" style="--control-select-color:${color}">
      <div class="mode-select">${rendered}</div>
    </div>`;
  }

  function renderTile(c) {
    const stateObj = S[c.entity];
    if (!stateObj) {
      return card(`<div class="preview-note">Tile: unbekannte Entity<br><code>${esc(c.entity)}</code></div>`);
    }
    const color = tileColor(stateObj, c.color);
    const name = esc(hass.formatEntityName(stateObj, c.name));
    const icon = c.icon || stateObj.attributes.icon || "information-outline";

    const content = [].concat(c.state_content || ["state"]);
    const stateBits = content.map((item) => {
      if (item === "state") return esc(hass.formatEntityState(stateObj));
      if (item === "last_changed" || item === "last_updated") return `<span class="muted">${relativeTime(stateObj._changed)}</span>`;
      const v = stateObj.attributes[item];
      return `<span class="muted">${esc(v === undefined ? "" : v)}</span>`;
    }).filter(Boolean);

    const style = color ? ` style="--tile-color:${color}"` : "";
    const iconStyle = color ? ` style="color:${color}"` : "";
    const pulse = stateObj.entity_id === ALARM && ["arming", "pending", "triggered"].includes(stateObj.state) ? " pulse" : "";
    const features = (c.features || [])
      .map((f) => (f.type === "alarm-modes" ? renderAlarmModesFeature(f, stateObj) : `<div class="feature preview-note">Feature <code>${esc(f.type)}</code> wird in der Vorschau nicht gezeichnet</div>`))
      .join("");

    return card(
      `<div class="tile${pulse}"${style}>
        <div class="tile-content">
          <div class="tile-icon"${iconStyle}>${svgIcon(icon)}</div>
          <div class="tile-info">
            <span class="tile-name">${name}</span>
            ${c.hide_state ? "" : `<span class="tile-state">${stateBits.join(" · ")}</span>`}
          </div>
        </div>
        ${features ? `<div class="tile-features">${features}</div>` : ""}
      </div>`
    );
  }

  function renderMarkdown(c, bannerColor) {
    let html;
    try {
      html = renderTemplate(c.content || "", {});
    } catch (err) {
      return card(`<div class="preview-note">Markdown-Vorlage konnte nicht ausgewertet werden:<br><code>${esc(err.message)}</code></div>`);
    }
    return `<div class="ha-card markdown-card banner" style="--banner-color:${bannerColor || "var(--divider-color)"}">${miniMarkdown(html)}</div>`;
  }

  /* Enough Markdown for the banners: headings, bold, italics, bullet lists.
     Consecutive plain lines form one paragraph, like CommonMark does it. */
  function miniMarkdown(text) {
    const lines = text.replace(/\r/g, "").split("\n");
    let out = "";
    let inList = false;
    let paragraph = [];

    const flushParagraph = () => {
      if (!paragraph.length) return;
      out += `<p>${inlineMd(paragraph.join(" "))}</p>`;
      paragraph = [];
    };
    const flushList = () => {
      if (!inList) return;
      out += "</ul>";
      inList = false;
    };

    for (const raw of lines) {
      const line = raw.trim();
      if (!line) {
        flushParagraph();
        continue;
      }
      if (/^[-*]\s+/.test(line)) {
        flushParagraph();
        if (!inList) { out += "<ul>"; inList = true; }
        out += `<li>${inlineMd(line.replace(/^[-*]\s+/, ""))}</li>`;
        continue;
      }
      flushList();
      if (/^#{2,3}\s+/.test(line)) {
        flushParagraph();
        out += `<h2>${inlineMd(line.replace(/^#{2,3}\s+/, ""))}</h2>`;
      } else {
        paragraph.push(line);
      }
    }
    flushParagraph();
    flushList();
    return out;
  }

  const inlineMd = (s) =>
    esc(s)
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

  function renderConditional(c) {
    if (!(c.conditions || []).every(conditionOk)) return "";
    const inner = c.card || {};
    // A red banner for the two alarm conditions, an amber one for open zones.
    let color = "var(--warning-color)";
    if (inner.type === "markdown") {
      const content = inner.content || "";
      if (/Alarm ausgelöst/.test(content)) color = "var(--error-color)";
      else if (/Störung der Alarmanlage/.test(content)) color = "var(--error-color)";
      else if (/Ausgangsverzögerung/.test(content)) color = "var(--orange-color)";
      else if (/Zonen offen/.test(content)) color = "var(--warning-color)";
    }
    return renderCard(inner, color);
  }

  function renderGrid(c) {
    const columns = c.columns || 4;
    const style = `grid-template-columns: repeat(${columns}, minmax(0, 1fr));`;
    return `<div class="card-grid" style="${style}">${renderCards(c.cards, c.square === false ? "stretch" : "")}</div>`;
  }

  function renderAlarmPanel(c) {
    const stateObj = S[c.entity];
    if (!stateObj) return card(`<div class="preview-note">Unbekannte Entity <code>${esc(c.entity)}</code></div>`);
    const color = stateColorCss(stateObj) || "var(--secondary-text-color)";
    const armed = ["armed_home", "armed_away", "armed_night", "arming", "pending", "triggered"].includes(stateObj.state);
    const buttons = [];
    if (!armed) {
      buttons.push(`<span class="ap-btn">${svgIcon("home")} Zuhause</span>`);
      buttons.push(`<span class="ap-btn primary">${svgIcon("lock")} Abwesend</span>`);
    } else {
      buttons.push(`<span class="ap-btn disarm">${svgIcon("shield-off")} Unscharf</span>`);
    }
    return card(
      `<div class="alarm-panel-card">
        <div class="ap-name">${esc(c.name || hass.formatEntityName(stateObj))}</div>
        <div class="ap-state" style="--state-color:${color}">${esc(hass.formatEntityState(stateObj))}</div>
        <div class="ap-buttons">${buttons.join("")}</div>
      </div>`,
      "alarm-panel-card"
    );
  }

  /* --- generated history, so the preview has something to draw ------------ */
  function historyFor(entityId, hours = 24) {
    const stateObj = S[entityId];
    const on = stateObj && stateObj.state === "on";
    const blocks = [];
    const seed = entityId.length;
    // deterministic pseudo-random open intervals
    for (let i = 0; i < 4; i++) {
      const start = ((seed * (i + 3) * 37) % 100) / 100 * hours;
      const len = 0.12 + ((seed * (i + 7) * 13) % 100) / 100 * 0.5;
      blocks.push([Math.max(0, start), Math.min(hours, start + len)]);
    }
    const now = new Date();
    if (on) {
      const hoursSince = Math.min(hours - 0.05, (stateObj._changed || 0) / 3600);
      blocks.push([hours - hoursSince, hours]);
    }
    void now;
    return blocks;
  }

  function renderHistoryGraph(c) {
    const hours = c.hours_to_show || 24;
    const rows = (c.entities || [])
      .map((e) => (typeof e === "string" ? { entity: e } : e))
      .map((e) => {
        const stateObj = S[e.entity];
        if (!stateObj) return "";
        const blocks = historyFor(e.entity, hours).filter(([a, b]) => b > a);
        const rects = blocks
          .map(([a, b]) => {
            const x = (a / hours) * 100;
            const w = ((b - a) / hours) * 100;
            return `<rect x="${x.toFixed(2)}%" y="6" width="${Math.max(w, 0.35).toFixed(2)}%" height="10" rx="1.5" fill="var(--state-active-color)"></rect>`;
          })
          .join("");
        return `<div class="history-row">
          <span class="hname">${esc(e.name || hass.formatEntityName(stateObj))}</span>
          <span class="strip"><svg viewBox="0 0 100 22" preserveAspectRatio="none">
            <rect x="0" y="6" width="100" height="10" rx="1.5" fill="var(--secondary-background-color)"></rect>
            ${rects}
          </svg></span>
        </div>`;
      })
      .join("");

    const now = new Date();
    const from = new Date(now.getTime() - hours * 3600 * 1000);
    const fmt = (d) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    return card(
      `<div class="card-header">${esc(c.title || "Verlauf")}</div>
       <div class="card-sub">Gelb = offen / aktiv · ${hours} Stunden</div>
       ${rows}
       <div class="history-axis"><span>${fmt(from)}</span><span>${fmt(new Date((from.getTime() + now.getTime()) / 2))}</span><span>jetzt</span></div>`,
      "history-card"
    );
  }

  function renderLogbook(c) {
    const hours = c.hours_to_show || 24;
    const targets = (c.target && c.target.entity_id) || [];
    const events = [];
    const st = S[ALARM];
    const add = (entityId, seconds, text) => {
      if (targets.length && !targets.includes(entityId)) return;
      if (seconds > hours * 3600) return;
      events.push({ seconds, name: hass.formatEntityName(S[entityId] || { attributes: {}, entity_id: entityId }), text, entityId });
    };

    const alarmText = {
      disarmed: "unscharf geschaltet",
      armed_away: "scharf geschaltet (abwesend)",
      armed_home: "scharf geschaltet (zuhause)",
      arming: "Scharfschaltung gestartet",
      triggered: "Alarm ausgelöst",
    };
    add(ALARM, 95, alarmText[st.state] || st.state);
    if (st.state === "armed_away") {
      const by = st.attributes.last_armed_by_user;
      events.push({
        seconds: Math.max(0, st._changed - 25),
        name: st.attributes.friendly_name,
        text: `von Schlüssel ${by} scharf geschaltet`,
        entityId: ALARM,
      });
      add(ALARM, 3600 + 40, "unscharf geschaltet");
    }
    for (const z of ZONES_PERIMETER) {
      const zs = S[z];
      add(z, (zs._changed || 0) + 5, zs.state === "on" ? "geöffnet" : "geschlossen");
      if (zs._changed > 120) add(z, (zs._changed || 0) + 900, "geschlossen");
      else add(z, (zs._changed || 0) + 2400, "geöffnet");
    }
    add("binary_sensor.crow_alarm_system_system_tamper", 4200, "Sabotagekontakt geprüft");

    events.sort((a, b) => a.seconds - b.seconds);
    const rows = events
      .slice(0, 18)
      .map((e) =>
        `<div class="logbook-entry">
           <span class="time">${clockTime(e.seconds)}</span>
           <span class="dot" style="background:${cssColor("var(--state-icon-color)")}"></span>
           <span class="body"><b>${esc(e.name)}</b> ${esc(e.text)}</span>
         </div>`
      )
      .join("");

    return card(
      `<div class="card-header">${esc(c.title || "Aktivität")}</div>
       <div class="row-divider"></div>
       ${rows || `<div class="logbook-entry"><span class="body">Keine Ereignisse.</span></div>`}`,
      "logbook-card"
    );
  }

  function renderCard(c, bannerColor) {
    if (!c || typeof c !== "object") return "";
    const t = c.type;
    switch (t) {
      case "heading": return renderHeading(c);
      case "tile": return renderTile(c);
      case "markdown": return renderMarkdown(c, bannerColor);
      case "conditional": return renderConditional(c);
      case "grid": return renderGrid(c);
      case "logbook": return renderLogbook(c);
      case "history-graph": return renderHistoryGraph(c);
      case "alarm-panel": return renderAlarmPanel(c);
      case "entity": return renderTile({ entity: c.entity, name: c.name, icon: c.icon, color: c.color, state_content: ["state"] });
      default: return card(`<div class="preview-note">Kartentyp <code>${esc(t)}</code> wird in der Vorschau nicht gezeichnet</div>`);
    }
  }

  function renderCards(cards, extraClass = "") {
    return (cards || [])
      .filter(visible)
      .map((c) => `<div class="card-slot ${extraClass}">${renderCard(c)}</div>`)
      .join("");
  }

  /* ==========================================================================
     8. The view
     ========================================================================== */
  function renderView() {
    const view = window.ALARM_VIEW;
    if (!view) throw new Error("cards.js is missing - run preview/build_cards.py");

    const headings = [view.title || "", view.subtitle ? `<div class="subtitle">${esc(view.subtitle)}</div>` : ""].join("");
    const badges = (view.badges || []).filter(visible).map(renderBadge).join("");

    const sections = view.sections
      .filter(visible)
      .map((section) => {
        const span = Math.min(section.column_span || 1, 4);
        return `<div class="ha-section sp-${span}">${renderCards(section.cards)}</div>`;
      })
      .join("");

    document.getElementById("view").innerHTML = `
      <div class="ha-header">
        <div class="title-row">
          <div><h1>${esc(view.title || "")}</h1>${view.subtitle ? `<div class="subtitle">${esc(view.subtitle)}</div>` : ""}</div>
          <div class="ha-badges">${badges}</div>
        </div>
      </div>
      <div class="ha-container">${sections}</div>`;
    void headings;

    setHarnessInfo();
  }

  /* ==========================================================================
     9. Harness (not part of the dashboard)
     ========================================================================== */
  function setHarnessInfo() {
    const el = document.getElementById("mode-value");
    if (el) el.textContent = S[EXPERT] ? S[EXPERT].state : "?";
    const count = document.getElementById("section-count");
    if (count) {
      const visibleSections = (window.ALARM_VIEW.sections || []).filter(visible).length;
      count.textContent = String(visibleSections);
    }
    const scenarioLabel = document.getElementById("scenario-value");
    if (scenarioLabel) scenarioLabel.textContent = SCENARIOS[scenarioKey].label;
  }

  function redraw() {
    buildStates();
    hass.states = S;
    renderView();
  }

  function init() {
    const scenarioSwitch = document.getElementById("scenario-switch");
    if (scenarioSwitch) {
      scenarioSwitch.innerHTML = Object.entries(SCENARIOS)
        .map(([key, s]) => `<button data-scenario="${key}"${key === scenarioKey ? ' class="active"' : ""}>${esc(s.label)}</button>`)
        .join("");
      scenarioSwitch.addEventListener("click", (ev) => {
        const btn = ev.target.closest("button[data-scenario]");
        if (!btn) return;
        scenarioKey = btn.dataset.scenario;
        [...scenarioSwitch.children].forEach((b) => b.classList.toggle("active", b === btn));
        redraw();
      });
    }

    const modeSwitch = document.getElementById("mode-switch");
    if (modeSwitch) {
      modeSwitch.addEventListener("click", (ev) => {
        const btn = ev.target.closest("button[data-mode]");
        if (!btn) return;
        const want = btn.dataset.mode;
        // toggle input_boolean.expert_mode, exactly like the badge does
        BASE[EXPERT][0] = want;
        BASE[EXPERT][1].lc = 1;
        [...modeSwitch.children].forEach((b) => b.classList.toggle("active", b === btn));
        redraw();
      });
    }

    const themeToggle = document.getElementById("theme-toggle");
    if (themeToggle) {
      themeToggle.addEventListener("click", () => {
        const dark = document.body.classList.toggle("dark");
        themeToggle.textContent = dark ? "☀︎ Light" : "☾ Dark";
      });
    }

    redraw();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
