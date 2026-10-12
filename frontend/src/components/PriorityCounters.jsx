import { countByPriority, PRIORITIES } from "../lib/alarm.js";

export default function PriorityCounters({ alarms }) {
  const counts = countByPriority(alarms);
  return (
    <section className="priority-grid" aria-label="Alarmes por prioridade">
      {PRIORITIES.map((priority) => (
        <article className={`priority-tile priority-${priority}`} key={priority}>
          <span>{priority}</span>
          <strong>{counts[priority]}</strong>
        </article>
      ))}
    </section>
  );
}
