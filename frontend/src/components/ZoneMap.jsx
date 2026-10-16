import { useEffect, useState } from "react";

import { formatTimestamp } from "../lib/alarm.js";
import { CONDITIONS, ZONE_STATES, zoneSummary } from "../lib/zoneMap.js";

/** Keyboard-accessible schematic and live device details; no alarm ACK here. */
export default function ZoneMap({ config, error, state, online }) {
  const [selected, setSelected] = useState(null);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (error) return <section className="error-banner" role="alert">Mapa: {error}</section>;
  if (!config) return <p role="status">Carregando mapa de zonas…</p>;
  const summaries = Object.fromEntries(config.zones.map((zone) => [zone.id,
    zoneSummary(zone, state, online, config.stale_after_seconds, now)]));
  const zone = config.zones.find((item) => item.id === selected) ?? config.zones[0];
  const detail = summaries[zone.id];
  return (
    <section className="zone-panel" aria-labelledby="zone-map-title">
      <header className="zone-heading">
        <div><small>MAPA 2D · ESQUEMÁTICO / SEM ESCALA</small>
          <h2 id="zone-map-title">{config.title}</h2></div>
        <span className="map-feed-state">{online ? "Eventos ao vivo" : "Fluxo indisponível"}</span>
      </header>
      <div className="zone-layout">
        <div className="zone-plan" role="group" aria-label="Zonas da propriedade">
          <svg className="zone-plan-base" viewBox="0 0 100 100" preserveAspectRatio="none"
            aria-hidden="true"><rect x="3" y="3" width="94" height="94" rx="1" />
            <path d="M3 36H97 M3 71H97 M50 36V71" /></svg>
          {config.zones.map((item) => {
            const summary = summaries[item.id];
            const status = ZONE_STATES[summary.state];
            return <button type="button" key={item.id} data-zone-id={item.id}
              className={`zone-indicator zone-${summary.state}`}
              style={{ left: `${item.x}%`, top: `${item.y}%`,
                width: `${item.width}%`, height: `${item.height}%` }}
              aria-pressed={zone.id === item.id} aria-controls="zone-detail"
              aria-label={`${item.name}: ${status.label}`}
              onClick={() => setSelected(item.id)}>
              <span className="zone-symbol" aria-hidden="true">{status.symbol}</span>
              <span className="zone-name">{item.name}</span>
              <span className="zone-status">{status.label}</span>
            </button>;
          })}
        </div>
        <aside className="zone-detail" id="zone-detail" aria-labelledby="zone-detail-title">
          <small>DETALHE DA ZONA</small>
          <h3 id="zone-detail-title">{zone.name}</h3>
          <p>Conta {zone.account_id} · Partição {zone.zone_partition} · Zona {zone.zone_number}</p>
          <strong className={`zone-detail-status zone-${detail.state}`}>
            {ZONE_STATES[detail.state].symbol} {ZONE_STATES[detail.state].label}
          </strong>
          {detail.conditions.length > 0 && <p>{detail.conditions.join(" · ")}</p>}
          {detail.stale && <p className="zone-stale">Sem confirmação recente de todos os dispositivos.
            {detail.conditions.length > 0 && " Falhas anteriores permanecem indicadas."}</p>}
          <ul className="zone-devices">
            {detail.devices.map((device) => <li key={device.id}>
              <strong>{device.id}</strong>
              {device.conditions.length === 0 ? <span>Sem evento confirmado</span>
                : device.conditions.map(([condition, item]) => <span key={condition}>
                  {CONDITIONS[condition]}: {item.active ? "ativa" : "restaurada"} · {item.code}
                  <time dateTime={new Date(item.timestamp).toISOString()}>
                    {formatTimestamp(item.timestamp)}</time>
                </span>)}
            </li>)}
          </ul>
        </aside>
      </div>
      <ul className="zone-legend" aria-label="Legenda do mapa">
        {Object.entries(ZONE_STATES).map(([key, value]) => <li key={key}>
          <span className={`legend-symbol zone-${key}`} aria-hidden="true">{value.symbol}</span>
          {value.label}</li>)}
      </ul>
      <p className="map-note">Estado observado nesta sessão. Restauração de zona não reconhece alarmes da lista.</p>
    </section>
  );
}
