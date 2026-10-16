# Sprint 2 — fechamento

Fechamento técnico local em 15/10/2026, após os Dias 11–18. Os incrementos
lógicos 19–20 consolidam integração, revisão do backlog e planejamento da Sprint 3;
não representam dois dias corridos consumidos. Base validada: commit `34896e2`.

## Resultado da meta

Sprint encerrada no recorte local documentado: integração de intrusão/câmeras IP,
mapa 2D esquemático e calendário aplicado ao PIR simulado. Homologação física e
certificação de protocolos não integram o aceite local. Não há declaração de
compatibilidade integral com qualquer modelo de central/câmera.

| Entrega | Evidência | Resultado e limite |
|---|---|---|
| E7-001, ONVIF T | Dias 11/13, smoke 12/13 | Cruzamento de linha → evento canônico → MQTT; câmera física pendente |
| E7-002, metadados | Dias 12/13, smoke 12/13 | Classificação pessoa/veículo por XML + RTSP/RTP; observações por callback, sem persistência/correlação automática |
| E7-003, SIA | Dia 14, smoke 14 | TCP ASCII, CRC, AES-128/256, subconjunto SIA-DCS e ACK após MQTT |
| E7-005, supervisão | Dia 15, smoke 15 | Timeout/retorno RP, alarme HIGH no banco e elegibilidade para R01 |
| E7-004, Contact ID | Dia 16, smoke 16 | ADM-CID sobre DC-09/TCP, códigos 130/137/602; não DTMF/socket proprietário |
| E6-007, mapa 2D | Dia 17, smoke 17 | Cadastro local e projeção por dispositivo; esquema sem planta física e sem snapshot histórico |
| E4-008, risco | Dia 18, smoke 18 | Agenda IANA, ajuste do PIR simulado e API/HMI; sem controle de sensibilidade física |

Os DoDs individuais preservam decisões, contagens e limites históricos. A entrega
dos metadados não fabrica intrusão nem converte classificação em BA. O contrato
canônico de eventos permanece intacto.

## Validação repetida no fechamento

| Verificação | Resultado |
|---|---|
| Suíte Python completa | 213 testes aprovados |
| Cobertura backend | 94%; calendário/rota de risco/PIR 100% |
| Suíte frontend | 17 testes aprovados |
| Cobertura V8 de `frontend/src/lib/*.js` | 96,25% de linhas; mapa e risco 100% |
| `flake8 backend tests` | Sem erros |
| Build Vite | Aprovado |
| Docker Compose | Mosquitto e TimescaleDB saudáveis |
| Smoke 9 | R01/R02, persistência e ACK no banco aprovados |
| Smoke 12 (inclui 11) | ONVIF por fixture e Mosquitto QoS 1 aprovados |
| Smoke 13 | RTSP Digest, TCP/RTP/XML, classificação e TEARDOWN aprovados |
| Smoke 14 | SIA TCP/AES-128/256, ACK, retry e rejeição aprovados |
| Smoke 15 | Supervisão real TCP/MQTT, HIGH, R01 CRITICAL, ACK e limpeza aprovados |
| Smoke 16 | Contact ID TCP/AES/MQTT/banco, idempotência e limpeza aprovados |
| Smoke 17 | MQTT → WebSocket → mapa, teclado, celular, reconexão e cadastro inválido aprovados |
| Smoke 18 | HTTP com relógio controlado → HMI, fronteiras e falha visível aprovados |

As mensagens de rejeição dos smokes 14/16 são esperadas para tráfego inválido.
As capturas regeneradas ficam em `tmp/day17` e `tmp/day18`, não versionadas;
desktop/mobile já foram inspecionados nos respectivos incrementos.
Os smokes que escrevem no banco removem seus dados por UUID. O smoke 17 publica
IDs sintéticos do simulador e não inicia consumer; um consumer externo em
execução poderia persistir esses eventos. Nenhum equipamento físico foi usado.

## Pendências repriorizadas

| Pendência | Destino/decisão |
|---|---|
| Modelo/manual/credenciais da central e câmeras; teste de bancada | Fora da Sprint 3 selecionada; desbloquear e repriorizar quando houver equipamento |
| Homologação de ONVIF/SIA/Contact ID e intervalos RP | Etapa física posterior, sem promessa de data ou compatibilidade |
| Metadados de objetos voláteis, sem armazenamento/associação ao cruzamento | Backlog técnico; requer política de associação e evidência física, sem transferir automaticamente |
| Deduplicação/supervisão voláteis, QoS 1 com possível redelivery | Limite aceito do MVP; durabilidade adicional fora da Sprint 3 selecionada |
| Mapa esquemático e estado desconhecido ao reconectar | Limite explícito; histórico será consultável na Sprint 3, sem prometer snapshot de estado do mapa |
| Risco altera somente PIR simulado; parâmetros de bancada | Não transferir controle físico nem calibração para a Sprint 3 |
| API sem autenticação; ACK com UUID fornecido pelo cliente; sem trilha de auditoria | Prioridade selecionada na Sprint 3 |
| Histórico/timeline/relatório ainda ausentes | Selecionados na Sprint 3, somente eventos canônicos persistidos |
| Clear, shelving, replay WebSocket, flood e R03 | Backlog explícito, fora do recorte selecionado da Sprint 3 |

Este fechamento não torna o MVP apto a exposição pública. JWT, auditoria e
permissões ainda serão implementados; a Sprint 2 não os entrega.

## Aprendizados e capacidade

- Definir transporte e política antes do código evitou tratar variantes de CID
  como equivalentes e preservou o schema único.
- Classificação de objeto, estado observado e alarme operacional precisam de
  contratos separados; heartbeat/ausência de incidentes não provam saúde de zona.
- Smokes com serviços reais complementam testes de relógio controlado e fixtures;
  validação local não substitui homologação.
- A documentação histórica não prova o estado atual; os DoDs e este fechamento
  registram os incrementos realmente entregues.
- Resposta do usuário para a Sprint 3: **“Sem disponibilidade fixa; prazo em aberto”**.
  Não há horas/dia, velocidade medida ou prazo comprometido. A próxima sprint
  será uma sequência completa de incrementos, dimensionada por dependências,
  sem transformar números de dias em estimativas de calendário.

## Encerramento e passagem

- [x] Incrementos e limites reconciliados com o plano.
- [x] Suíte, cobertura, lint, build e integrações repetidos.
- [x] Backlog e pendências repriorizados em `BACKLOG_STATUS.md`.
- [x] Plano integral da Sprint 3 registrado antes de qualquer implementação.
- [x] Auto-revisão e verificação de ausência de segredos no diff documental.

Próximo documento: [plano completo da Sprint 3](SPRINT3_PLAN.md). A Sprint 3
fica planejada, ainda não iniciada. O novo chat deverá ler esse plano e este
fechamento; não repetir a Sprint 2 ou tratar o roadmap histórico como compromisso.

O documento mestre e o handoff em `../DOCUMENTAÇÕES/`, fora da raiz Git do
repositório, receberam notas de continuidade locais. Os registros versionados
que acompanham este fechamento são os arquivos em `docs/` e o README.
