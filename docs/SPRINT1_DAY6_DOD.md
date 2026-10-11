# Sprint 1 - Dia 6 - Definition of Done

## Escopo entregue

- [x] E3-007 - Cenário completo `wall_jump`.
- [x] Quatro eventos canônicos publicados no MQTT pela CLI.
- [x] Sequência Sísmico -> Feixe IV -> PIR -> Câmera IVA.

## Contratos implementados

- Sensor sísmico em `t=0s`: código `SA`, prioridade `HIGH`.
- Feixe IV em `t=2s`: bloqueio de 180 ms, código `BA`, `CRITICAL`.
- PIR em `t=4s`: detecção térmica, código `BA`, `CRITICAL`.
- Câmera IVA em `t=6s`: cruzamento de linha, código `BA`, `CRITICAL`.
- Todos os eventos usam exatamente os onze campos do payload fixo.
- Conta, dispositivos, zonas, tempos e geometria ficam no `config.yaml`.

## Verificações do DoD

- [x] 81 testes automatizados passam.
- [x] Cobertura total de 96% (meta: maior ou igual a 80%).
- [x] `flake8` passa sem erros.
- [x] Funções e classes possuem docstrings.
- [x] Smoke test MQTT recebeu quatro eventos em 0,047 segundo.
- [x] Auto-revisão concluída.

A história E3-007 fica concluída após todas as verificações acima.
