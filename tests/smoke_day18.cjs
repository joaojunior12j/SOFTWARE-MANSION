/** Controlled-clock HTTP API -> HMI risk modes, timeout/failure and screenshots. */
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.env.PSIM_PLAYWRIGHT_MODULE || "playwright");
const root = path.resolve(__dirname, "..");
const output = path.join(root, "tmp", "day18");
fs.mkdirSync(output, { recursive: true });
const clockFile = path.join(output, "clock.txt");
const python = process.env.PSIM_PYTHON || path.join(root, ".venv", "Scripts", "python.exe");
const setClock = (value) => fs.writeFileSync(clockFile, value);

async function run() {
  setClock("2026-10-19T01:59:59+00:00");
  const api = spawn(python, ["-m", "uvicorn", "tests.risk_smoke_app:create_smoke_app",
    "--factory", "--host", "127.0.0.1", "--port", "8001"], {
    cwd: root, env: { ...process.env, PSIM_RISK_SMOKE_CLOCK: clockFile },
    windowsHide: true, stdio: "ignore",
  });
  let browser;
  try {
    const started = Date.now();
    while (true) {
      try { if ((await fetch("http://127.0.0.1:8001/api/risco")).ok) break; } catch {}
      if (api.exitCode !== null || Date.now() - started > 15000) throw new Error("Smoke API failed to start");
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({ channel: "msedge", headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/api/risco", async (route) => {
      const response = await route.fetch({ url: "http://127.0.0.1:8001/api/risco" });
      await route.fulfill({ response });
    });
    await page.goto("http://127.0.0.1:5173");
    await page.getByText("Modo padrão", { exact: true }).waitFor();
    setClock("2026-10-19T02:00:00+00:00");
    await page.reload();
    await page.getByText("Risco elevado", { exact: true }).waitFor();
    await page.getByText("Horário configurado · America/Sao_Paulo", { exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, "desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, "mobile.png"), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    setClock("2026-10-19T03:00:00+00:00");
    await page.reload();
    await page.getByText("Modo padrão", { exact: true }).waitFor();
    setClock("2027-01-01T03:00:00+00:00");
    await page.reload();
    await page.getByText("Data configurada · America/Sao_Paulo", { exact: true }).waitFor();
    await page.unroute("**/api/risco");
    await page.route("**/api/risco", (route) => route.fulfill({ status: 503 }));
    await page.reload();
    await page.getByText("Calendário indisponível", { exact: true }).waitFor();
    assert.equal(await page.getByText("Modo padrão", { exact: true }).count(), 0);
    assert.deepEqual(errors, []);
    console.log("risk_http=ok weekly_boundary=ok date_boundary=ok hmi=ok failure_unknown=ok mobile=ok screenshots=tmp/day18");
  } finally {
    if (browser) await browser.close();
    api.kill();
  }
}
run().catch((error) => { console.error(error); process.exitCode = 1; });
