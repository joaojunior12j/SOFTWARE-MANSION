export const PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export function countByPriority(alarms) {
  return PRIORITIES.reduce((counts, priority) => {
    counts[priority] = alarms.filter(
      (alarm) => alarm.priority_level === priority,
    ).length;
    return counts;
  }, {});
}

export function describeCodes(alarm) {
  const codes = alarm.sia_codes ?? [];
  if (codes.length > 0) {
    return codes.join(" · ");
  }
  return alarm.rule_triggered ?? "SEM CÓDIGO";
}

export function formatTimestamp(value, locale = "pt-BR") {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

export function websocketUrl(locationLike = window.location) {
  const protocol = locationLike.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${locationLike.host}/api/eventos/stream`;
}

export function isUuid(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
  );
}
