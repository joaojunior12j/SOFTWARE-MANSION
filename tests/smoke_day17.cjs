/** Real MQTT -> API WebSocket -> React zone map; local synthetic simulator IDs.
 * Requires running API/Vite/Mosquitto and Playwright (or PSIM_PLAYWRIGHT_MODULE).
 * No database writes are made by this script. A running consumer may persist events.
 */
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { chromium } = require(process.env.PSIM_PLAYWRIGHT_MODULE || "playwright");

const root = path.resolve(__dirname, "..");
const python = process.env.PSIM_PYTHON || path.join(root, ".venv", "Scripts", "python.exe");
const output = path.join(root, "tmp", "day17");
fs.mkdirSync(output, { recursive: true });
const publishCode = `
import json, sys
from uuid import uuid4
import paho.mqtt.client as mqtt
from backend.api.schemas import AlarmEvent
from backend.core.event_bus import EventPublisher
from backend.core.settings import load_settings
settings = load_settings()['mqtt']
event = AlarmEvent.model_validate(json.load(sys.stdin))
publisher = EventPublisher(settings['host'], settings['port'], settings['keepalive'],
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'psim-map-smoke-{uuid4()}'))
try:
    publisher.connect()
    publisher.publish(event, timeout=5)
finally:
    publisher.close()
`;

function publish(overrides = {}) {
  const event = { event_id: randomUUID(), timestamp: new Date().toISOString(),
    account_id: "1234", source_type: "PERIMETER_SENSOR",
    device_hardware_id: "PIR-PERIMETRO-NORTE", zone_partition: "01", zone_number: 2,
    sia_code: "BA", event_status: "ACTIVE", priority_level: "CRITICAL",
    correlation_id: null, ...overrides };
  execFileSync(python, ["-c", publishCode], {
    cwd: root, input: JSON.stringify(event), stdio: ["pipe", "pipe", "pipe"], timeout: 15000,
  });
}

async function run() {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => {
      const NativeWebSocket = window.WebSocket;
      window.WebSocket = class extends NativeWebSocket {
        constructor(...args) { super(...args); window.smokeSocket = this; }
      };
    });
    await page.goto("http://127.0.0.1:5173");
    await page.getByText("Eventos ao vivo", { exact: true }).waitFor();
    const pir = page.locator('[data-zone-id="pir-norte"]');
    assert.match(await pir.getAttribute("class"), /zone-UNKNOWN/);
    publish({ account_id: "9999" });
    publish({ device_hardware_id: "UNCONFIGURED-SMOKE" });
    publish();
    await page.locator('[data-zone-id="pir-norte"].zone-CRITICAL').waitFor();
    await pir.focus();
    await page.keyboard.press("Enter");
    assert.equal(await pir.getAttribute("aria-pressed"), "true");
    await page.getByRole("heading", { name: "Faixa de detecção", exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, "desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, "mobile.png"), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    publish({ sia_code: "RP", priority_level: "LOW" });
    await page.waitForTimeout(400);
    assert.match(await pir.getAttribute("class"), /zone-CRITICAL/);
    publish({ sia_code: "BR", event_status: "RESTORED", priority_level: "LOW" });
    await page.locator('[data-zone-id="pir-norte"].zone-RESTORED').waitFor();
    // Simulate status polling during a broker outage; transport stays open.
    await page.route("**/api/status", (route) => route.fulfill({ json: { mqtt_online: false } }));
    await page.locator('[data-zone-id="pir-norte"].zone-UNKNOWN').waitFor();
    await page.unroute("**/api/status");
    await page.getByText("Eventos ao vivo", { exact: true }).waitFor();
    assert.match(await pir.getAttribute("class"), /zone-UNKNOWN/);
    publish({ sia_code: "BR", event_status: "RESTORED", priority_level: "LOW" });
    await page.locator('[data-zone-id="pir-norte"].zone-RESTORED').waitFor();
    await page.evaluate(() => window.smokeSocket.close());
    await page.locator('[data-zone-id="pir-norte"].zone-UNKNOWN').waitFor();
    await page.getByText("Eventos ao vivo", { exact: true }).waitFor();
    assert.match(await pir.getAttribute("class"), /zone-UNKNOWN/);
    await context.close();

    const invalid = await browser.newContext();
    const invalidPage = await invalid.newPage();
    await invalidPage.route("**/zone-map.json", (route) => route.fulfill({
      json: { title: "Broken", zones: [] },
    }));
    await invalidPage.goto("http://127.0.0.1:5173");
    await invalidPage.getByRole("alert").filter({ hasText: "Cadastro do mapa inválido" }).waitFor();
    assert.equal(await invalidPage.locator("[data-zone-id]").count(), 0);
    await invalid.close();
    assert.deepEqual(errors, []);
    console.log("mqtt_websocket_map=ok keyboard=ok mobile=ok heartbeat=ok restore=ok broker_status=ok reconnect=ok invalid_config=ok screenshots=tmp/day17");
  } finally {
    await browser.close();
  }
}
run().catch((error) => { console.error(error); process.exitCode = 1; });
