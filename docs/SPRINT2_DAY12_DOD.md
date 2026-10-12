# Sprint 2 - Dia 12 - Definition of Done

## Escopo do incremento

E7-002 no documento mestre solicita receber metadados de classificação de
pessoa/veículo. Este incremento entrega a decodificação e recepção de documentos
XML completos por uma fonte injetável. A história E7-002 permanece parcial:
a conexão ao stream de uma câmera e a homologação física ainda estão pendentes.

Critérios de aceite deste incremento:

- [x] Interpretar `tt:MetaDataStream/tt:VideoAnalytics/tt:Frame/tt:Object`.
- [x] Ler `Human` e `Vehicle` em `Class/Type` e no legado `ClassCandidate`.
- [x] Preservar timestamp com timezone, ObjectId, Source e contexto da câmera.
- [x] Preservar candidatos e confiança, sem escolher uma classificação vencedora.
- [x] Confiança ausente permanece desconhecida; valores inválidos são rejeitados.
- [x] Ignorar classes desconhecidas sem inferir pessoa/veículo por outros campos.
- [x] Rejeitar XML inválido, namespaces incorretos, DTDs e documentos excessivos.
- [x] Validar o documento inteiro antes de entregar observações ao callback.
- [x] Manter o payload de `backend/api/schemas.py` exatamente intacto.

## Decisão de contrato

Uma classificação de objeto descreve a cena; ela não comprova intrusão.
`CameraObjectMetadata` é um contrato imutável em memória, entregue por callback,
sem campos SIA, estado de alarme ou prioridade. Não é publicado nos tópicos
`eventos/#` e não alimenta o CEP como se fosse um novo `BA`. Nenhum tópico MQTT,
schema de banco ou contrato REST foi acrescentado neste incremento.

O caminho Profile T de cruzamento de linha continua publicando eventos canônicos
via MQTT. Associar uma observação ao cruzamento exige identificador de objeto,
origem e tempo reais; este incremento não inventa essa associação.

## Verificações

- [x] 138 testes Python aprovados, incluindo 15 novos testes de comportamento.
- [x] Cobertura total 92%; módulo novo `onvif_metadata.py`: 99% (meta: 80%).
- [x] `flake8 backend tests` aprovado.
- [x] Docstrings, CLI de inspeção e configuração `metadata_max_bytes` documentadas.
- [x] Auto-revisão: contrato, validação, isolamento dos alarmes e limites verificados.
- [x] Smoke: fixture sintética decodificada e regressão Profile T entregue pelo
  Mosquitto real com payload canônico. Não há transporte Profile M real neste smoke.
- [x] Revisão dos arquivos alterados sem IP, usuário ou senha reais.

```powershell
python -m tests.smoke_day12
python -m coverage run --source=backend -m unittest discover -s tests -v
python -m coverage report -m --fail-under=80
python -m flake8 backend tests
```

## Referências e limites

Fixture sintética baseada nas estruturas oficiais, não em captura de equipamento:

- [ONVIF Profile M](https://www.onvif.org/profiles/profile-m/).
- [Analytics 22.06, seção 5.1.3.5](https://www.onvif.org/specs/2206/Analytics.html).
- [Analytics 19.06, descritor legado](https://www.onvif.org/specs/srv/analytics/ONVIF-Analytics-Service-Spec-v1906.pdf).

O limite de XML é configurado em `integrations.onvif.metadata_max_bytes`.
`lxml`, já utilizado por zeep, foi declarado como dependência direta por ser
importado pelo novo adaptador. Imagens, faces, placas e extensões de fabricante
não são retidas. Observações não são persistidas nem exibidas na HMI.

Próximo incremento de E7-002: descoberta da capacidade de metadados da câmera,
transporte RTSP/RTP com remontagem dos documentos, timeout/reconexão e gestão
segura de credenciais. `run()` recebe documentos completos; não é um parser de
pacotes RTP ou fragmentos XML. A fonte controla timeouts e cancelamento de leituras
bloqueadas. Falhas de parsing e callbacks são propagadas ao supervisor.

Não declarar E7-002 completa ou Profile M homologado sem essas etapas.
