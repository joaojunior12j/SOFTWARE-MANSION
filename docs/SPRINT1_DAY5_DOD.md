# Sprint 1 - Dia 5 - Definition of Done

## Escopo entregue

- [x] E5-001 - WebSocket `WS /api/eventos/stream` em tempo real.
- [x] E5-002 - Endpoint `GET /api/alarmes/ativos`.
- [x] Aplicação FastAPI e documentação OpenAPI.
- [x] Ponte MQTT para distribuição de eventos validados no WebSocket.

## Contratos implementados

- Somente eventos compatíveis com o payload JSON canônico são transmitidos.
- O WebSocket recebe eventos via MQTT, sem polling.
- Alarmes ativos são todos os estados ISA-18.2 exceto `CLEARED`.
- A lista é ordenada por `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` e timestamp.
- A API usa a configuração central para banco, MQTT, conta e CORS.

## Verificações do DoD

- [x] 76 testes automatizados passam.
- [x] Cobertura total de 92%; módulos novos entre 88% e 100%.
- [x] `flake8` passa sem erros.
- [x] Funções e classes possuem docstrings.
- [x] Integração local com MQTT e PostgreSQL validada.
- [x] Evento MQTT entregue no WebSocket em 0,016 segundo no smoke test.
- [x] Auto-revisão concluída.

As histórias E5-001 e E5-002 atendem ao escopo e ao DoD do Dia 5.
