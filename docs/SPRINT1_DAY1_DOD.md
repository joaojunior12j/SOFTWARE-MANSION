# Sprint 1 - Dia 1 - Definition of Done

## Escopo entregue

- [x] Repositório Git inicializado na branch `main`.
- [x] Estrutura de pastas do documento mestre criada.
- [x] Ambiente virtual Python criado em `.venv` e ignorado pelo Git.
- [x] Mosquitto configurado para o ambiente local da Sprint 1.
- [x] PostgreSQL 16 + TimescaleDB declarados no Docker Compose.
- [x] Schema SQL idempotente criado com `events` como hypertable.
- [x] `config.yaml` centralizado criado com os parâmetros do documento mestre.
- [x] Payload fixo preservado no contrato da tabela `events`.
- [x] Segredos locais mantidos em `.env`, ignorado pelo Git.

## Verificações do DoD

- [x] Cinco testes de contrato de infraestrutura passam.
- [x] `flake8` passa sem erros em `backend` e `tests`.
- [x] Os dois arquivos YAML passam no parser PyYAML.
- [x] Funções e classes de teste possuem docstrings.
- [x] Auto-revisão concluída contra os documentos de referência.
- [x] `docker compose config` e `docker compose up` executados.
- [x] Inicialização real do schema e health checks dos dois serviços validados.

## Evidências de integração

- Mosquitto e TimescaleDB iniciaram com estado `healthy`.
- Extensões `pgcrypto` 1.3 e `timescaledb` 2.15.3 confirmadas no banco.
- Tabelas `users`, `devices`, `correlations`, `events`, `alarms` e
  `alarm_shelving` confirmadas.
- Tabela `events` confirmada como hypertable de uma dimensão temporal.
- Payload JSON canônico inserido com sucesso em uma transação de teste revertida.
- Publicação e assinatura MQTT confirmadas em `mansao/1234/eventos/#`.

As histórias E1-001 a E1-005 atendem ao escopo e ao DoD do Dia 1.

