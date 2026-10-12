# PSIM Mansion

Fundacao do supervisório de segurança eletrônica descrito em
`../DOCUMENTAÇÕES/SCRUM_PSIM_MANSION.md`.

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
o payload canônico. A conexão RTSP/RTP à câmera ainda está pendente.

Inspecione a fixture sintética ou um documento XML capturado localmente:

```powershell
python -m backend.integrations.onvif_metadata tests/fixtures/onvif_object_metadata.xml --account 1234 --camera-id CAMERA-TEST --partition 01 --zone 3
python -m tests.smoke_day12
```

O limite de tamanho fica em `integrations.onvif.metadata_max_bytes`. O smoke
verifica a decodificação da fixture e a regressão do caminho Profile T pelo
Mosquitto real; não homologa uma câmera Profile M. Veja os critérios de aceite e
pendências em [DoD do Dia 12](docs/SPRINT2_DAY12_DOD.md).

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

