import assert from "node:assert/strict";
import test from "node:test";

import { describeRisk } from "../src/lib/risk.js";

const data = { mode: "ELEVATED", reason: "weekly_hour", scope: "SIMULATOR_PIR",
  evaluated_at: "2026-10-19T02:00:00Z", timezone: "America/Sao_Paulo",
  pir_alpha_multiplier: 1.5 };

test("risk indicator names each valid server mode and reason", () => {
  for (const [mode, label, reason] of [["ELEVATED", "Risco elevado", "weekly_hour"],
    ["STANDARD", "Modo padrão", "outside_schedule"],
    ["DISABLED", "Calendário desativado", "disabled"],
    ["ELEVATED", "Risco elevado", "configured_date"]]) {
    assert.equal(describeRisk({ ...data, mode, reason }, 1000, 1000).label, label);
  }
});

test("expired data, clock reversal and failed queries cannot imply standard risk", () => {
  assert.equal(describeRisk(data, 1000, 36000).mode, "ELEVATED");
  assert.equal(describeRisk(data, 1000, 36001).mode, "UNKNOWN");
  assert.equal(describeRisk(data, 1000, 999).mode, "UNKNOWN");
  assert.equal(describeRisk(null, 1000, 1000).mode, "UNKNOWN");
  assert.equal(describeRisk(data, null, 1000).mode, "UNKNOWN");
});

test("malformed policy snapshots remain unavailable", () => {
  for (const change of [{ mode: "unexpected" }, { mode: "constructor" },
    { reason: "__proto__" }, { scope: "PHYSICAL_SENSOR" },
    { evaluated_at: "invalid" }, { timezone: null }, { timezone: "" },
    { pir_alpha_multiplier: Infinity }, { pir_alpha_multiplier: 0 },
    { pir_alpha_multiplier: 4 }]) {
    assert.equal(describeRisk({ ...data, ...change }, 1000, 1000).mode, "UNKNOWN");
  }
});
