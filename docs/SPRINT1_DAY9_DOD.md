# Sprint 1 - Dia 9 - Definition of Done

## Escopo entregue

- [x] E4-002 - R01 Jammer dentro da janela de 15 segundos.
- [x] E4-003 - R02 com três dispositivos distintos em 60 segundos.
- [x] E5-003 - Reconhecimento de alarmes conforme ISA-18.2.

## Contratos implementados

- R01 exige câmera `DISCONNECTED`, central `TIMEOUT_SIA_DC09` e PIR `BA`.
- R01 cria alarme `R01_JAMMER`, `CRITICAL`, confiança `0.95`.
- R02 exige códigos `BA` ou `SA` de pelo menos três dispositivos distintos.
- R02 cria alarme `R02_MULTI_SENSOR`, `CRITICAL`, confiança `0.98`.
- Eventos já correlacionados não geram incidentes duplicados.
- Alarmes correlacionados iniciam em `UNACKNOWLEDGED`.
- ACK aceita somente `UNACKNOWLEDGED -> ACKNOWLEDGED`.
- ACK persiste `acknowledged_by` e `acknowledged_at` sob bloqueio transacional.

## Verificações do DoD

- [x] 114 testes automatizados passam.
- [x] Cobertura total de 97% (meta: maior ou igual a 80%).
- [x] `flake8` passa sem erros.
- [x] Funções e classes possuem docstrings.
- [x] Smoke real detecta R01 e R02 e persiste o ACK.
- [x] Auto-revisão concluída.

As histórias E4-002, E4-003 e E5-003 ficam concluídas após as verificações.
