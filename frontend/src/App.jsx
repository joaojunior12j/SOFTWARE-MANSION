import { useEffect, useState } from "react";

import AcknowledgeDialog from "./components/AcknowledgeDialog.jsx";
import AlarmList from "./components/AlarmList.jsx";
import PriorityCounters from "./components/PriorityCounters.jsx";
import StatusBar from "./components/StatusBar.jsx";
import ZoneMap from "./components/ZoneMap.jsx";
import { useAlarmFeed } from "./hooks/useAlarmFeed.js";
import { useZoneMap } from "./hooks/useZoneMap.js";
import { isUuid } from "./lib/alarm.js";

const STORED_OPERATOR = "psim_operator_id";

export default function App() {
  const map = useZoneMap();
  const feed = useAlarmFeed(map.acceptEvent, map.reset);
  const [operatorId, setOperatorId] = useState(
    () => localStorage.getItem(STORED_OPERATOR) || "",
  );
  const [selectedAlarm, setSelectedAlarm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    if (isUuid(operatorId)) {
      localStorage.setItem(STORED_OPERATOR, operatorId);
    } else {
      localStorage.removeItem(STORED_OPERATOR);
    }
  }, [operatorId]);

  const requestAcknowledge = (alarm) => {
    setActionError("");
    if (!isUuid(operatorId)) {
      setActionError("Informe um UUID válido para o operador antes de reconhecer.");
      return;
    }
    setSelectedAlarm(alarm);
  };

  const confirmAcknowledge = async () => {
    setBusy(true);
    setActionError("");
    try {
      const response = await fetch(
        `/api/alarmes/${selectedAlarm.alarm_id}/acknowledge`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ acknowledged_by: operatorId }),
        },
      );
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || "Falha ao reconhecer o alarme");
      }
      setSelectedAlarm(null);
      await feed.refreshAlarms();
    } catch (reason) {
      setActionError(reason.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">M</span>
          <div><small>SECURITY OPERATIONS</small><h1>PSIM MANSION</h1></div>
        </div>
        <StatusBar
          lastUpdate={feed.lastUpdate}
          mqttOnline={feed.mqttOnline}
          streamOnline={feed.streamOnline}
        />
      </header>

      <main>
        <section className="page-heading">
          <div><small>VISÃO OPERACIONAL</small><h2>Alarmes ativos</h2></div>
          <label className="operator-field">
            <span>UUID DO OPERADOR</span>
            <input
              aria-invalid={operatorId !== "" && !isUuid(operatorId)}
              onChange={(event) => setOperatorId(event.target.value.trim())}
              placeholder="00000000-0000-4000-8000-000000000000"
              value={operatorId}
            />
          </label>
        </section>

        <PriorityCounters alarms={feed.alarms} />
        {(feed.error || actionError) && (
          <div className="error-banner" role="alert">
            {actionError || feed.error}
          </div>
        )}
        <ZoneMap config={map.config} error={map.error} state={map.state}
          online={feed.streamOnline && feed.mqttOnline} />
        <h2 className="alarm-section-title">Lista de alarmes</h2>
        <AlarmList alarms={feed.alarms} onAcknowledge={requestAcknowledge} />
      </main>

      <footer className="app-footer">
        <span>ISA-101 / ISA-18.2</span>
        <span>{feed.alarms.length} alarme(s) ativo(s)</span>
      </footer>

      {selectedAlarm && (
        <AcknowledgeDialog
          alarm={selectedAlarm}
          busy={busy}
          onCancel={() => setSelectedAlarm(null)}
          onConfirm={confirmAcknowledge}
        />
      )}
    </div>
  );
}
