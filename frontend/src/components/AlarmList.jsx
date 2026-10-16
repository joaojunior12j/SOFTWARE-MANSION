import AlarmCard from "./AlarmCard.jsx";

export default function AlarmList({ alarms, onAcknowledge }) {
  if (alarms.length === 0) {
    return (
      <div className="empty-state">
        <span aria-hidden="true">✓</span>
        <h2>Nenhum alarme ativo</h2>
        <p>Nenhum incidente na lista. Consulte o mapa para os estados observados.</p>
      </div>
    );
  }
  return (
    <section className="alarm-list" aria-label="Lista de alarmes ativos">
      {alarms.map((alarm) => (
        <AlarmCard
          alarm={alarm}
          key={alarm.alarm_id}
          onAcknowledge={onAcknowledge}
        />
      ))}
    </section>
  );
}
