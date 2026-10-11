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

