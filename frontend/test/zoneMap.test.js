import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { applyZoneEvent, validateZoneMap, zoneSummary } from "../src/lib/zoneMap.js";

const config = JSON.parse(readFileSync(new URL("../public/zone-map.json", import.meta.url)));
const now = Date.parse("2026-10-15T15:00:00Z");
const zone = config.zones[0];
function event(overrides = {}) {
  return { account_id: zone.account_id, zone_partition: zone.zone_partition,
    zone_number: zone.zone_number, device_hardware_id: zone.devices[0],
    event_id: "synthetic-1", timestamp: new Date(now).toISOString(),
    source_type: "PERIMETER_SENSOR", sia_code: "BA", event_status: "ACTIVE",
    priority_level: "CRITICAL", ...overrides };
}
const apply = (state, overrides = {}) => applyZoneEvent(state, event(overrides), config, now);
const summary = (state, online = true, clock = now) => zoneSummary(zone, state, online, 120, clock);

test("local simulator layout is valid and bounded", () => {
  assert.equal(validateZoneMap(config), config);
  for (const bad of [null, {}, { ...config, title: "" },
    { ...config, zones: [] }, { ...config, zones: Array(101).fill(zone) },
    { ...config, stale_after_seconds: 0 }, { ...config, stale_after_seconds: Infinity },
    { ...config, stale_after_seconds: 86401 }, { ...config, zones: [null] }]) {
    assert.throws(() => validateZoneMap(bad), /Cadastro/);
  }
});

test("reject invalid geometry, identifiers, devices and duplicate addresses", () => {
  for (const change of [{ id: "" }, { id: "__proto__" }, { name: "" }, { account_id: "" },
    { zone_partition: "" }, { zone_number: -1 }, { zone_number: 1000 },
    { x: -1 }, { y: -1 }, { width: 0 }, { height: 0 }, { x: 99 }, { y: 99 },
    { x: NaN }, { devices: [] }, { devices: ["same", "same"] },
    { devices: [""] }, { devices: ["constructor"] }, { devices: Array(33).fill("a") }]) {
    assert.throws(() => validateZoneMap({ ...config, zones: [{ ...zone, ...change }] }));
  }
  assert.throws(() => validateZoneMap({ ...config, zones: [zone, { ...zone, id: "other" }] }));
  assert.throws(() => validateZoneMap({ ...config, zones: [zone,
    { ...zone, zone_number: 50 }] }));
});

test("initially unknown; an RP heartbeat never proves a healthy zone", () => {
  assert.equal(summary({}).state, "UNKNOWN");
  assert.deepEqual(apply({}, { sia_code: "RP" }), {});
  const state = {};
  assert.equal(applyZoneEvent(state, null, config), state);
});

test("unconfigured account, partition, zone or device never changes projection", () => {
  const state = {};
  for (const change of [{ account_id: "9999" }, { zone_partition: "02" },
    { zone_number: 99 }, { device_hardware_id: "other" },
    { timestamp: "invalid" }, { timestamp: new Date(now + 30001).toISOString() },
    { priority_level: "wrong" }]) {
    assert.equal(apply(state, change), state);
  }
  assert.equal(applyZoneEvent(state, event(), null), state);
});

test("restoration is scoped to device and condition, never an entire zone", () => {
  let state = apply({});
  state = apply(state, { device_hardware_id: zone.devices[1],
    event_status: "RESTORED", sia_code: "BR", priority_level: "LOW" });
  assert.equal(summary(state).state, "CRITICAL");
  state = apply(state, { event_status: "TAMPER", sia_code: "TA", priority_level: "HIGH" });
  state = apply(state, { timestamp: new Date(now + 1000).toISOString(),
    event_status: "RESTORED", sia_code: "BR", priority_level: "LOW" });
  assert.equal(summary(state).state, "HIGH");
  assert.deepEqual(summary(state).conditions, ["Tamper"]);
  state = apply(state, { timestamp: new Date(now + 2000).toISOString(),
    event_status: "RESTORED", sia_code: "TR", priority_level: "LOW" });
  assert.equal(summary(state).state, "RESTORED");
  assert.equal(summary(state, false).state, "UNKNOWN");
  assert.equal(summary(state, true, now + 122001).state, "UNKNOWN");
});

test("unobserved devices prevent a restored state, even after another returns", () => {
  const state = apply({}, { event_status: "RESTORED", sia_code: "BR" });
  assert.equal(summary(state).state, "UNKNOWN");
  assert.equal(summary(state).devices[1].latest, null);
});

test("worst active priority wins and faults survive stale/offline status", () => {
  for (const priority of ["LOW", "MEDIUM", "HIGH", "CRITICAL"]) {
    let state = apply({}, { priority_level: priority });
    assert.equal(summary(state).state, priority);
    assert.equal(summary(state, false).state, priority);
    assert.equal(summary(state, true, now + 120001).stale, true);
    state = apply(state, { device_hardware_id: zone.devices[1], priority_level: "CRITICAL" });
    assert.equal(summary(state).state, "CRITICAL");
  }
});

test("duplicates, same-time ambiguity and older restoration cannot clear a fault", () => {
  const state = apply({});
  assert.equal(apply(state), state);
  assert.equal(apply(state, { timestamp: new Date(now - 1).toISOString(),
    sia_code: "BR", event_status: "RESTORED" }), state);
  assert.equal(apply(state, { sia_code: "BR", event_status: "RESTORED" }), state);
});

test("communication is independent: heartbeat and tamper restoration cannot clear it", () => {
  for (const status of ["DISCONNECTED", "TIMEOUT_SIA_DC09"]) {
    let state = apply({}, { event_status: status, sia_code: "RP", priority_level: "HIGH" });
    state = apply(state, { sia_code: "RP" });
    state = apply(state, { sia_code: "TR", event_status: "RESTORED" });
    assert.deepEqual(summary(state).conditions, ["Comunicação"]);
    state = apply(state, { sia_code: "RP", event_status: "RESTORED",
      timestamp: new Date(now + 1000).toISOString() });
    assert.equal(summary(state).conditions.length, 0);
  }
});

test("SA intrusion supported, other codes do not mutate state; memory is bounded", () => {
  assert.equal(summary(apply({}, { sia_code: "SA" })).state, "CRITICAL");
  const state = apply({});
  assert.equal(apply(state, { sia_code: "FA" }), state);
  assert.equal(apply(state, { sia_code: "UNKNOWN", event_status: "RESTORED" }), state);
  let updated = state;
  for (let i = 1; i < 100; i++) {
    updated = apply(updated, { timestamp: new Date(now + i).toISOString() });
  }
  assert.equal(Object.keys(updated).length, 1);
  assert.equal(Object.keys(updated[zone.id]).length, 1);
  assert.equal(Object.keys(updated[zone.id][zone.devices[0]]).length, 1);
});
