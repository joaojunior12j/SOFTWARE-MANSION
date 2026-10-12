import assert from "node:assert/strict";
import test from "node:test";

import {
  countByPriority,
  describeCodes,
  isUuid,
  websocketUrl,
} from "../src/lib/alarm.js";

test("countByPriority returns every ISA priority", () => {
  const counts = countByPriority([
    { priority_level: "CRITICAL" },
    { priority_level: "CRITICAL" },
    { priority_level: "HIGH" },
  ]);
  assert.deepEqual(counts, { CRITICAL: 2, HIGH: 1, MEDIUM: 0, LOW: 0 });
});

test("describeCodes prefers SIA codes and falls back to the rule", () => {
  assert.equal(describeCodes({ sia_codes: ["BA", "SA"] }), "BA · SA");
  assert.equal(describeCodes({ rule_triggered: "R01_JAMMER" }), "R01_JAMMER");
});

test("websocketUrl mirrors secure and insecure page protocols", () => {
  assert.equal(
    websocketUrl({ protocol: "http:", host: "localhost:5173" }),
    "ws://localhost:5173/api/eventos/stream",
  );
  assert.equal(
    websocketUrl({ protocol: "https:", host: "hmi.example" }),
    "wss://hmi.example/api/eventos/stream",
  );
});

test("isUuid accepts operator UUIDs and rejects incomplete values", () => {
  assert.equal(isUuid("9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"), true);
  assert.equal(isUuid("operator-1"), false);
});
