# Sprint 1 - Dia 2 - Definition of Done

## Escopo entregue

- [x] E2-001 - Publisher MQTT com payload JSON canônico e QoS 1.
- [x] E2-002 - Consumer MQTT com validação e persistência no TimescaleDB.
- [x] E2-003 - Tópicos hierárquicos definidos e protegidos por testes.

## Contratos implementados

- Payload com os onze campos definidos no documento mestre.
- Campos extras são rejeitados.
- Timestamp sem fuso horário é rejeitado.
- Câmeras usam `mansao/{id}/eventos/cameras/{camera}/analytics`.
- Demais eventos normalizados usam `mansao/{id}/eventos/centrais`.
- Consumer assina `mansao/{id}/eventos/#`.
- Controle do simulador permanece em `mansao/{id}/simulador/controle`.
- Persistência é idempotente pela chave `(event_id, timestamp)`.
- Payload original é preservado na coluna `raw_payload`.

## Verificações do DoD

- [x] 35 testes automatizados passam.
- [x] Cobertura de código: 87%.
- [x] `flake8` passa sem erros.
- [x] Funções e classes possuem docstrings.
- [x] Variáveis de conexão são resolvidas por `config.yaml` e `.env`.
- [x] Auto-revisão concluída.
- [x] Integração publisher -> Mosquitto -> consumer -> TimescaleDB validada.
- [x] Registro criado pelo smoke test removido ao final.

As histórias E2-001, E2-002 e E2-003 atendem ao escopo e ao DoD do Dia 2.
