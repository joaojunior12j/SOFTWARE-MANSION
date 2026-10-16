/** Bounded live projection. A heartbeat never establishes a healthy zone. */
export const ZONE_STATES = {
  CRITICAL: { symbol: "!", label: "Crítica" },
  HIGH: { symbol: "▲", label: "Alta prioridade" },
  MEDIUM: { symbol: "◆", label: "Atenção" },
  LOW: { symbol: "●", label: "Aviso" },
  UNKNOWN: { symbol: "?", label: "Sem confirmação" },
  RESTORED: { symbol: "✓", label: "Restaurada" },
};
const PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
export const CONDITIONS = {
  intrusion: "Intrusão", tamper: "Tamper", communication: "Comunicação",
};

function address(value) {
  return JSON.stringify([value.account_id, value.zone_partition, value.zone_number]);
}

/** Validate a finite, unambiguous local layout before rendering it. */
export function validateZoneMap(config) {
  const text = (value) => typeof value === "string" && value.trim().length > 0
    && value.length <= 100;
  const identifier = (value) => text(value)
    && !["__proto__", "constructor", "prototype"].includes(value);
  const number = (value) => typeof value === "number" && Number.isFinite(value);
  if (!config || !text(config.title) || !Array.isArray(config.zones)
      || config.zones.length < 1 || config.zones.length > 100
      || !number(config.stale_after_seconds) || config.stale_after_seconds < 1
      || config.stale_after_seconds > 86400) {
    throw new Error("Cadastro do mapa inválido: título, zonas ou prazo.");
  }
  const ids = new Set(), addresses = new Set();
  for (const zone of config.zones) {
    if (!zone || !identifier(zone.id) || !text(zone.name) || !text(zone.account_id)
        || !text(zone.zone_partition) || !Number.isInteger(zone.zone_number)
        || zone.zone_number < 0 || zone.zone_number > 999
        || ![zone.x, zone.y, zone.width, zone.height].every(number)
        || zone.x < 0 || zone.y < 0 || zone.width <= 0 || zone.height <= 0
        || zone.x + zone.width > 100 || zone.y + zone.height > 100
        || !Array.isArray(zone.devices) || zone.devices.length < 1
        || zone.devices.length > 32 || !zone.devices.every(identifier)
        || new Set(zone.devices).size !== zone.devices.length
        || ids.has(zone.id) || addresses.has(address(zone))) {
      throw new Error("Cadastro do mapa inválido: zona, dispositivo ou duplicata.");
    }
    ids.add(zone.id);
    addresses.add(address(zone));
  }
  return config;
}

function conditionOf(event) {
  if (["DISCONNECTED", "TIMEOUT_SIA_DC09"].includes(event.event_status)) {
    return ["communication", true];
  }
  if (event.event_status === "TAMPER") return ["tamper", true];
  if (event.event_status === "ACTIVE" && ["BA", "SA"].includes(event.sia_code)) {
    return ["intrusion", true];
  }
  if (event.event_status === "RESTORED") {
    return { BR: ["intrusion", false], TR: ["tamper", false],
      RP: ["communication", false] }[event.sia_code];
  }
  return null;
}

/** Ignore unknown devices, invalid messages, retries and older condition updates. */
export function applyZoneEvent(state, event, config, now = Date.now()) {
  if (!config || !event || !PRIORITIES.includes(event.priority_level)) return state;
  const zone = config.zones.find((item) => address(item) === address(event)
    && item.devices.includes(event.device_hardware_id));
  const condition = conditionOf(event);
  const timestamp = Date.parse(event.timestamp);
  if (!zone || !condition || !Number.isFinite(timestamp)
      || timestamp > now + 30000) return state;
  const [name, active] = condition;
  const device = state[zone.id]?.[event.device_hardware_id] ?? {};
  if (device[name] && device[name].timestamp >= timestamp) return state;
  return {
    ...state,
    [zone.id]: {
      ...state[zone.id],
      [event.device_hardware_id]: {
        ...device,
        [name]: { active, timestamp, priority: event.priority_level,
          code: event.sia_code, eventId: event.event_id },
      },
    },
  };
}

/** Aggregate independent conditions without allowing another device to clear them. */
export function zoneSummary(zone, state, online, staleSeconds, now = Date.now()) {
  const devices = zone.devices.map((id) => {
    const conditions = Object.entries(state[zone.id]?.[id] ?? {});
    const latest = Math.max(...conditions.map(([, item]) => item.timestamp));
    return { id, conditions, latest: Number.isFinite(latest) ? latest : null,
      stale: !online || !Number.isFinite(latest) || now - latest > staleSeconds * 1000 };
  });
  const active = devices.flatMap((device) => device.conditions
    .filter(([, item]) => item.active).map(([name, item]) => ({ ...item, name })));
  const priority = PRIORITIES.find((value) => active.some((item) => item.priority === value));
  const stale = devices.some((device) => device.stale);
  return { state: priority ?? (stale ? "UNKNOWN" : "RESTORED"), stale, devices,
    conditions: [...new Set(active.map((item) => CONDITIONS[item.name]))] };
}
