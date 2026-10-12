import { describeCodes, formatTimestamp } from "../lib/alarm.js";

export default function AlarmCard({ alarm, onAcknowledge }) {
  const unacknowledged = alarm.state === "UNACKNOWLEDGED";
  const critical = alarm.priority_level === "CRITICAL";
  const classes = [
    "alarm-card",
    `alarm-${alarm.priority_level}`,
    critical && unacknowledged ? "alarm-pulse" : "",
  ].filter(Boolean).join(" ");

  return (
    <article className={classes} data-alarm-id={alarm.alarm_id}>
      <header>
        <span className="priority-label">{alarm.priority_level}</span>
        <span className={`alarm-state state-${alarm.state}`}>
          {alarm.state}
        </span>
      </header>
      <div className="alarm-content">
        <div>
          <small>INCIDENTE</small>
          <h2>{alarm.title}</h2>
          <p>{alarm.description || "Sem descrição adicional."}</p>
        </div>
        <dl>
          <div><dt>CÓDIGO</dt><dd>{describeCodes(alarm)}</dd></div>
          <div><dt>ZONA</dt><dd>{alarm.zone_partition || "—"}</dd></div>
          <div><dt>DISPARO</dt><dd>{formatTimestamp(alarm.triggered_at)}</dd></div>
        </dl>
      </div>
      <footer>
        {unacknowledged ? (
          <button type="button" onClick={() => onAcknowledge(alarm)}>
            Reconhecer alarme
          </button>
        ) : (
          <span className="acknowledged-label">
            Reconhecido em {formatTimestamp(alarm.acknowledged_at)}
          </span>
        )}
      </footer>
    </article>
  );
}
