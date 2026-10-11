# Sprint 1 - Dia 7 - Definition of Done

## Escopo entregue

- [x] E3-008 - Cenário completo `rf_jammer`.
- [x] Três eventos canônicos publicados no MQTT pela CLI.
- [x] Sequência câmera offline -> timeout SIA DC-09 -> PIR ativo.

## Contratos implementados

- Câmera `DISCONNECTED` em `t=0s`, na partição `01`.
- Central `TIMEOUT_SIA_DC09` em `t=5s`, na mesma partição.
- PIR `BA/ACTIVE` em `t=10s`, na mesma partição.
- A sequência completa permanece dentro da janela R01 de 15 segundos.
- Todos os eventos usam exatamente os onze campos do payload fixo.
- Conta, dispositivos, zonas e tempos ficam no `config.yaml`.
- O motor CEP e a emissão de `R01_JAMMER` permanecem nos Dias 8 e 9.

## Verificações do DoD

- [x] 89 testes automatizados passam.
- [x] Cobertura total de 96% (meta: maior ou igual a 80%).
- [x] `flake8` passa sem erros.
- [x] Funções e classes possuem docstrings.
- [x] Smoke test MQTT recebeu três eventos em 0,047 segundo.
- [x] Auto-revisão concluída.

A história E3-008 fica concluída após todas as verificações acima.
