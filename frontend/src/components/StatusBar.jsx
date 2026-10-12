import { formatTimestamp } from "../lib/alarm.js";

export default function StatusBar({ mqttOnline, streamOnline, lastUpdate }) {
  const online = mqttOnline && streamOnline;
  return (
    <div className="status-bar" aria-live="polite">
      <div className={`connection-state ${online ? "online" : "offline"}`}>
        <span className="status-dot" aria-hidden="true" />
        <div>
          <small>BARRAMENTO MQTT</small>
          <strong>{online ? "ONLINE" : "OFFLINE"}</strong>
        </div>
      </div>
      <div className="last-update">
        <small>ÚLTIMA ATUALIZAÇÃO</small>
        <time>{formatTimestamp(lastUpdate)}</time>
      </div>
    </div>
  );
}
