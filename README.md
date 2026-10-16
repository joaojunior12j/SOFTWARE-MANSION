# PSIM Mansion

Fundacao do supervisório de segurança eletrônica descrito em
`../DOCUMENTAÇÕES/SCRUM_PSIM_MANSION.md`.

## Escopo da versão em desenvolvimento

Decisão do usuário de 15/10/2026: concluir esta versão integrando apenas intrusão
(centrais/sensores) e câmeras IP. Controle de acesso fica fora de todas as sprints
desta versão, apenas como possibilidade eventual de atualização futura, sem esforço
ou compromisso agora, evitando custos de protocolos, leituras e integrações
desnecessários. Reconhecimento facial não é entrega comprometida nem nova frente.
Os analíticos são embarcados na câmera; o PSIM recebe, normaliza, correlaciona e
registra eventos, sem analisar imagens. Câmeras analógicas estão fora do escopo.
A validação é local, com simulador e possível equipamento de bancada; homologação
física fica para um segundo momento. Ao fechar cada sprint, planejar toda a
seguinte, conforme a seção 11.1 do documento mestre.

## Dia 1 - infraestrutura

O ambiente local contém apenas os componentes previstos para o Dia 1:

- Eclipse Mosquitto 2.0 como barramento MQTT;
- PostgreSQL 16 com TimescaleDB;
- schema SQL inicial e idempotente;
- configuração central em `config/config.yaml`;
- estrutura de diretórios da aplicação para as próximas histórias.

Nenhum publisher, consumer, endpoint, simulador ou frontend foi implementado nesta
etapa inicial.

## Dia 2 - Event Bus

O publisher e o consumer usam o payload único definido no documento mestre.

Publicar um evento salvo em JSON:

```powershell
python -m backend.core.event_bus caminho\evento.json
```

Executar o consumer que persiste `mansao/1234/eventos/#` no TimescaleDB:

```powershell
python -m backend.db.consumer
```

## Dia 3 - Modelos PIR e Feixe IV

O simulador possui os dois primeiros modelos matemáticos previstos:

- PIR com probabilidade de detecção dependente da temperatura ambiente;
- Feixe IV com decisões `IGNORE`, `SUSPICIOUS` e `ALARM` conforme a duração
  do bloqueio.

Os parâmetros ficam em `config/config.yaml`, e ambos os modelos expõem um
processo compatível com o relógio de eventos discretos do SimPy.

## Dia 4 - Câmera IVA e CLI

O modelo de câmera IVA detecta o cruzamento completo de uma linha virtual
finita. A CLI está preparada para executar os cenários à medida que forem
registrados nos próximos dias da Sprint 1:

```powershell
python simulate.py --list-scenarios
python simulate.py --scenario wall_jump --account 1234
```

O cenário `wall_jump` será registrado no Dia 6; até lá, a segunda chamada
retorna um erro explícito em vez de produzir eventos fictícios.

## Dia 5 - API de alarmes e eventos

Inicie a API com:

```powershell
python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

- `GET /api/alarmes/ativos` lista os alarmes ainda não limpos por prioridade.
- `WS /api/eventos/stream` transmite eventos MQTT canônicos sem polling.
- `/docs` apresenta a documentação OpenAPI interativa.

Com Mosquitto e TimescaleDB ativos, execute a validação ponta a ponta com:

```powershell
python -m tests.smoke_day5
```

## Dia 6 - Cenário wall_jump

Execute o cenário documentado de invasão pelo muro:

```powershell
python simulate.py --scenario wall_jump --account 1234
```

A CLI publica quatro eventos MQTT canônicos na sequência Sísmico, Feixe IV,
PIR e Câmera IVA. O smoke test dedicado pode ser executado com:

```powershell
python -m tests.smoke_day6
```

## Dia 7 - Cenário rf_jammer

Execute a sequência que alimentará a regra de correlação R01:

```powershell
python simulate.py --scenario rf_jammer --account 1234
```

A CLI publica, na mesma partição e dentro de 15 segundos, os eventos de câmera
desconectada, timeout SIA DC-09 e PIR ativo. Valide a integração MQTT com:

```powershell
python -m tests.smoke_day7
```

## Dia 8 - Motor CEP base

O consumidor MQTT mantém janelas deslizantes isoladas por conta e partição,
descarta eventos expirados e persiste correlações com um `correlation_id`
comum a todos os eventos do incidente. As regras R01 e R02 serão registradas
no Dia 9.

Com o TimescaleDB ativo, valide a persistência real com:

```powershell
python -m tests.smoke_day8
```

## Dia 9 - Regras CEP e reconhecimento

O consumidor registra as regras `R01_JAMMER` e `R02_MULTI_SENSOR`, cria alarmes
`CRITICAL` e disponibiliza a transição ISA-18.2:

```http
POST /api/alarmes/{alarm_id}/acknowledge
Content-Type: application/json

{"acknowledged_by":"UUID-DO-OPERADOR"}
```

Valide regras, banco e reconhecimento com:

```powershell
python -m tests.smoke_day9
```

## Dia 10 - HMI operacional

A interface React 18 + Vite apresenta os alarmes ativos em tempo real, com
contadores e cores por prioridade, estado MQTT, códigos SIA, zona e horário.
Alarmes críticos não reconhecidos possuem indicação pulsante. O reconhecimento
exige confirmação e um UUID de operador válido.

Com a API e o consumidor em execução, inicie a HMI:

```powershell
cd frontend
npm install
npm run dev
```

Acesse `http://localhost:5173`. Para validar a projeção real do alarme e a
persistência do reconhecimento no PostgreSQL, execute na raiz do projeto:

```powershell
python -m tests.smoke_day10
```

Validações isoladas do frontend:

```powershell
cd frontend
npm test
npm run build
npm audit
```

## Sprint 2 - Dia 11 - ONVIF Profile T

O listener ONVIF usa PullPoint para receber o tópico padronizado
`RuleEngine/LineDetector/Crossed` e o traduz para o payload JSON canônico antes
da publicação MQTT. IP, usuário e senha da câmera não são versionados.

Defina `ONVIF_CAMERA_PASSWORD` somente no `.env` local e execute:

```powershell
python -m backend.integrations.onvif_listener `
  --host ENDERECO_LOCAL_DA_CAMERA `
  --username USUARIO_LOCAL `
  --account 1234 `
  --camera-id CAMERA-MURO-NORTE `
  --partition 01 `
  --zone 3
```

O listener aceita também `--port` e `--password-env`. A câmera deve estar na
rede local protegida e possuir eventos analíticos ONVIF habilitados. Para
validar a normalização e a entrega MQTT sem depender de hardware físico:

```powershell
python -m tests.smoke_day11
```

## Sprint 2 - Dia 12 - Metadados ONVIF (incremento de E7-002)

O adaptador `backend.integrations.onvif_metadata` recebe documentos XML completos
de uma fonte injetável e decodifica classificações `Human` e `Vehicle`. Preserva
o horário, identificador do objeto, origem e confiança da câmera. A classificação
fica em um contrato separado em memória e não gera alarme de intrusão ou altera
o payload canônico. O transporte RTSP/RTP foi implementado no Dia 13.

Inspecione a fixture sintética ou um documento XML capturado localmente:

```powershell
python -m backend.integrations.onvif_metadata tests/fixtures/onvif_object_metadata.xml --account 1234 --camera-id CAMERA-TEST --partition 01 --zone 3
python -m tests.smoke_day12
```

O limite de tamanho fica em `integrations.onvif.metadata_max_bytes`. O smoke
verifica a decodificação da fixture e a regressão do caminho Profile T pelo
Mosquitto real; não homologa uma câmera Profile M. Veja os critérios de aceite e
pendências em [DoD do Dia 12](docs/SPRINT2_DAY12_DOD.md).

## Sprint 2 - Dia 13 - Transporte ONVIF RTSP/RTP

O processo consulta os perfis ONVIF Media1 com analytics metadata habilitado e
recebe a trilha XML `vnd.onvif.metadata` por RTP intercalado em TCP. Inclui Digest
MD5/SHA-256, timeout, keepalive, reconexão e liberação da sessão. Classificações
continuam separadas dos eventos de alarme e são impressas como observações JSON.

Defina `ONVIF_CAMERA_HOST`, `ONVIF_CAMERA_PORT`, `ONVIF_CAMERA_USERNAME` e
`ONVIF_CAMERA_PASSWORD` no `.env` local. Execute:

```powershell
python -m backend.integrations.onvif_stream --account 1234 --camera-id CAMERA-LOCAL --partition 01 --zone 3
python -m tests.smoke_day13
```

Use `--profile-token` para selecionar um perfil específico. Os parâmetros de
transporte ficam em `integrations.onvif` na configuração central. O smoke usa um
servidor RTSP sintético por socket de loopback e Mosquitto real; a homologação
com câmera física permanece pendente. Suporte: Media1, RTSP 1.0, TCP intercalado,
XML sem compressão. Consulte os demais limites no
[DoD do Dia 13](docs/SPRINT2_DAY13_DOD.md).

## Sprint 2 - Dia 14 - Receptor SIA-DCS TCP

O receptor valida enquadramento, tamanho, CRC, conta e timestamp antes de
normalizar BA/BR/TA/TR/RP para o JSON canônico. Suporta AES-CBC-128/256 e envia
ACK criptografado após confirmação MQTT QoS 1. NULL é um controle sem evento.

Defina `SIA_ACCOUNT_ID`, `SIA_DEVICE_ID` e `SIA_AES_KEY` no `.env` local.
A chave deve ter 32 ou 64 dígitos hexadecimais; nunca a versione. Execute:

```powershell
python -m backend.integrations.sia_dc09_listener
python -m tests.smoke_day14
```

O bind padrão é loopback:5500, configurável em `integrations.sia_dc09`.
Texto aberto fica desabilitado por padrão. A CLI configura uma conta por
processo. O smoke usa contas e chaves sintéticas, TCP local e Mosquitto real.
Homologação com central física permanece pendente. Supervisão de RP e o
subconjunto ADM-CID foram acrescentados nos Dias 15 e 16, descritos abaixo.
Consulte o [DoD do Dia 14](docs/SPRINT2_DAY14_DOD.md) e o
[plano de continuidade](docs/SPRINT2_PLAN.md) para escopo e limites.

## Sprint 2 - Dia 15 - Supervisão SIA e alarme de comunicação

O receptor monitora RP válido por conta, com prazo inicial de 60s configurável.
Ao expirar, publica um único `TIMEOUT_SIA_DC09` HIGH; um RP novo após a falha
gera retorno `RESTORED` LOW. Prazos usam relógio monotônico. Rejeições e
retransmissões não renovam o monitor. O modo `any_valid_message` permite usar
NULL e outros frames válidos, sem fabricar eventos RP a partir de NULL.

O consumer grava o alarme de comunicação HIGH sem impedir que o timeout participe
da R01. Retorno não reconhece nem limpa alarmes automaticamente. Para carregar
as alterações, reinicie o receptor e o consumer nos seus terminais:

```powershell
python -m backend.db.consumer
python -m backend.integrations.sia_dc09_listener
```

A configuração fica em `integrations.sia_dc09.supervision`; há prazo default,
overrides por conta, intervalo de verificação e opção de desativação explícita.
A fila MQTT do receptor também possui limite. Valide com:

```powershell
python -m tests.smoke_day15
```

O smoke usa TCP/AES, Mosquitto e TimescaleDB reais, com dispositivos e operador
sintéticos. Confira os limites e evidências no
[DoD do Dia 15](docs/SPRINT2_DAY15_DOD.md). Homologação física permanece pendente.

## Sprint 2 - Dia 16 - Contact ID sobre DC-09/TCP

O mesmo receptor aceita `ADM-CID`/`*ADM-CID`, com payload como
`#1234|1130 02 001`: qualificador 1/3, código, partição e zona. O recorte
normaliza 130 (intrusão) para BA/BR e 137 (tamper) para TA/TR. O teste periódico
1602 gera RP e renova a supervisão após validação/publicação. Outros códigos e
variantes são rejeitados sem ACK. O contrato JSON permanece intacto.

Use a configuração e as variáveis SIA já descritas. Inicie **um** receptor:

```powershell
python -m backend.integrations.contact_id_listener
python -m tests.smoke_day16
```

O comando é uma entrada alternativa para o mesmo serviço SIA/Contact ID na porta
5500; não execute ambos os listeners simultaneamente. AES-128/256, CRC,
timestamp, limites, ACK após MQTT e deduplicação são compartilhados.
O smoke verifica TCP → Mosquitto → TimescaleDB, com dados sintéticos e limpeza
por UUID. DTMF telefônico, socket proprietário e dados estendidos não estão
implementados. Consulte o [DoD do Dia 16](docs/SPRINT2_DAY16_DOD.md).
Compatibilidade com a central real depende de confirmar modelo/manual e homologar.

## Sprint 2 - Dia 17 - Mapa 2D de zonas

A HMI apresenta um mapa esquemático com seleção por mouse/teclado e detalhe dos
dispositivos. Cada estado usa texto, símbolo e cor; zonas sem confirmação ficam
neutras. RP não apaga intrusão, e a restauração de um dispositivo não limpa outro.
O mapa usa eventos do WebSocket existente; reconhecer alarmes continua na lista.

Edite `frontend/public/zone-map.json` para cadastrar conta, partição, número de
zona, dispositivos e retângulos em percentuais (`x`, `y`, `width`, `height`).
O cadastro inicial corresponde ao simulador da conta `1234`, não à planta real.
Adapte os IDs aos equipamentos provisionados antes de utilizá-los. O prazo
`stale_after_seconds` vale 120s para a confirmação local. Recarregue a página
após editar; em produção, gere novamente o build.

Ao abrir/reconectar, o mapa exige nova evidência. Não carrega estado histórico.
Falhas conhecidas permanecem indicadas enquanto a sessão perde confirmação;
retorno de conexão reinicia essa projeção. A lista de alarmes mantém seu fluxo
persistido separado. Consulte [política e DoD do Dia 17](docs/SPRINT2_DAY17_DOD.md).

```powershell
cd frontend
npm test -- --experimental-test-coverage --test-coverage-include=src/lib/zoneMap.js
npm run build
npm run dev
```

Com API e Mosquitto locais ativos, o cenário existente alimenta o mapa:

```powershell
python -m backend.simulator.cli --scenario wall_jump --account 1234
```

## Sprint 2 - Dia 18 - Calendário de risco

O calendário em `config/config.yaml` eleva automaticamente a sensibilidade do
PIR **simulado** nas horas/datas cadastradas. A HMI mostra o modo e o fuso via
`GET /api/risco`. Não altera sensores físicos, analytics de câmeras ou regras
R01/R02. O contrato dos eventos permanece intacto.

```yaml
risk_calendar:
  enabled: true
  timezone: "America/Sao_Paulo"
  pir_alpha_multiplier: 1.5
  high_risk_times:
    - weekday: 6  # Segunda = 0; domingo = 6
      hour: 23    # 23:00 inclusive até 00:00 exclusive
  high_risk_holidays:
    - "2027-04-21"  # Data local cadastrada, dia inteiro
```

Entradas sobrepostas não acumulam ajustes. Fora das janelas, o PIR usa o alpha
base; no risco elevado, usa alpha × multiplicador (limite 1–3). O `p_base` e o
zero de probabilidade sem contraste térmico permanecem. O valor 1.5 é inicial de
bancada, sem calibração com hardware. Os cenários usam a hora da detecção simulada,
independente da velocidade de execução.

As datas são uma agenda local, sem importação automática de feriados oficiais.
Reinicie API e simulador após editar. Bloco ausente mantém comportamento legado;
`enabled: false` desativa o ajuste. Fuso/datas/horas inválidos falham explicitamente.
No Windows, a dependência `tzdata` fornece a base IANA.

```powershell
python -m pip install -r requirements.txt
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

A HMI consulta o modo a cada 30s, com timeout de 5s. Consulta com falha ou sem
confirmação recente aparece indisponível. [Política, testes e limites do Dia 18](docs/SPRINT2_DAY18_DOD.md).

## Pre-requisitos

- Docker com o plugin Docker Compose;
- Python 3.11 ou superior para o desenvolvimento das próximas histórias.

## Inicialização

1. Copie `.env.example` para `.env` e troque a senha de desenvolvimento.
2. Crie e ative um ambiente virtual Python.
3. Instale as dependências com `python -m pip install -r requirements-dev.txt`.
4. Execute `docker compose up -d`.
5. Verifique os serviços com `docker compose ps`.

Na primeira criação do volume, o PostgreSQL executa automaticamente
`database/init/001_schema.sql`. O script também pode ser reaplicado com segurança.

## Verificações

```powershell
python -m unittest discover -s tests -v
python -m flake8 backend tests
python -m coverage run --source=backend -m unittest discover -s tests
python -m coverage report -m --fail-under=80
docker compose config
docker compose up -d
docker compose ps
```

O host configurado no `config.yaml` é `localhost`, apropriado para os processos
Python executados na máquina de desenvolvimento. Quando um processo Python for
containerizado, o host interno deverá ser configurado por ambiente como `database`.

