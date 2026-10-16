/** Display only a recent, validated server policy snapshot. */
export function describeRisk(snapshot, receivedAt, now = Date.now()) {
  const modes = { STANDARD: "Modo padrão", ELEVATED: "Risco elevado",
    DISABLED: "Calendário desativado" };
  const reasons = { weekly_hour: "Horário configurado", configured_date: "Data configurada",
    outside_schedule: "Fora das janelas configuradas", disabled: "Sem ajuste automático" };
  if (!snapshot || !Object.hasOwn(modes, snapshot.mode)
      || !Object.hasOwn(reasons, snapshot.reason) || snapshot.scope !== "SIMULATOR_PIR"
      || !Number.isFinite(receivedAt) || now < receivedAt || now - receivedAt > 35000
      || !Number.isFinite(Date.parse(snapshot.evaluated_at))
      || typeof snapshot.timezone !== "string" || !snapshot.timezone
      || !Number.isFinite(snapshot.pir_alpha_multiplier)
      || snapshot.pir_alpha_multiplier < 1 || snapshot.pir_alpha_multiplier > 3) {
    return { mode: "UNKNOWN", label: "Calendário indisponível", reason: "Sem consulta recente confirmada" };
  }
  return { mode: snapshot.mode, label: modes[snapshot.mode], reason: reasons[snapshot.reason] };
}
