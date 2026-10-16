import { useEffect, useState } from "react";

import { describeRisk } from "../lib/risk.js";

/** Poll server policy; failures and expired snapshots never imply standard risk. */
export default function RiskStatus() {
  const [data, setData] = useState(null);
  const [receivedAt, setReceivedAt] = useState(null);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    let stopped = false;
    let controller;
    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      try {
        const response = await fetch("/api/risco", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("Risk query failed");
        const snapshot = await response.json();
        if (!stopped) {
          setData(snapshot);
          setReceivedAt(Date.now());
          setNow(Date.now());
        }
      } catch {
        if (!stopped) setData(null);
      } finally {
        clearTimeout(timeout);
      }
    };
    load();
    const poll = setInterval(load, 30000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => { stopped = true; controller?.abort(); clearInterval(poll); clearInterval(tick); };
  }, []);
  const status = describeRisk(data, receivedAt, now);
  return <section className={`risk-status risk-${status.mode}`} aria-label="Calendário de risco">
    <span className="risk-symbol" aria-hidden="true">{status.mode === "ELEVATED" ? "◆" : "◷"}</span>
    <div aria-live="polite"><strong>{status.label}</strong><p>{status.reason}
      {status.mode !== "UNKNOWN" && ` · ${data.timezone}`}</p></div>
    <span className="risk-scope">Ajuste de sensibilidade: PIR do simulador</span>
  </section>;
}
