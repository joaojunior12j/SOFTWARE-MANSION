import { useEffect, useRef } from "react";

export default function AcknowledgeDialog({ alarm, busy, onCancel, onConfirm }) {
  const cancelRef = useRef(null);
  useEffect(() => cancelRef.current?.focus(), []);
  return (
    <div className="dialog-backdrop" role="presentation">
      <section
        aria-describedby="ack-description"
        aria-labelledby="ack-title"
        aria-modal="true"
        className="dialog"
        role="dialog"
      >
        <small>CONFIRMAÇÃO OPERACIONAL</small>
        <h2 id="ack-title">Reconhecer este alarme?</h2>
        <p id="ack-description">
          {alarm.title}. Esta ação registra o operador e interrompe a indicação
          piscante, mas não limpa o incidente.
        </p>
        <div className="dialog-actions">
          <button ref={cancelRef} type="button" onClick={onCancel} disabled={busy}>
            Cancelar
          </button>
          <button className="primary" type="button" onClick={onConfirm} disabled={busy}>
            {busy ? "Registrando…" : "Confirmar reconhecimento"}
          </button>
        </div>
      </section>
    </div>
  );
}
