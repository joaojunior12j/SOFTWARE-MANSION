# Sprint 2 - Dia 15 - Supervisão da comunicação SIA

## Escopo E7-005

Supervisionar contas provisionadas no receptor SIA do Dia 14, publicar timeout e
retorno no contrato canônico e apresentar um alarme de comunicação isolado.
A política e a complementação do consumer foram registradas antes de codificar
no [plano da Sprint 2](SPRINT2_PLAN.md).

## Política implementada

- Supervisão inicia na criação do receptor, sem depender de conexão TCP prévia.
  O prazo inicial é a tolerância para o primeiro heartbeat.
- Default do MVP: RP suportado, validado e novo renova o prazo. BA e NULL não
  renovam nessa política. O modo opcional `any_valid_message` aceita qualquer
  frame suportado e válido, incluindo NULL; ele não transforma NULL em RP.
- Rejeições de CRC, conta, chave, sintaxe ou timestamp não renovam a supervisão.
  Retransmissões no cache e timestamps de heartbeat não crescentes são ignorados.
- A mensagem só é considerada aceita após publicação bem-sucedida do evento
  original, ou validação de NULL sem evento, seguindo a política escolhida.
- Prazos usam relógio monotônico. Eventos locais usam timestamp UTC de detecção
  ou recebimento do retorno, sem reaproveitar um horário antigo da central.
- Timeout por conta configurável: default 60s; verificação default a cada 1s.
  São valores iniciais de bancada, ainda não homologados com uma central.

| Transição | Código | Estado canônico | Prioridade |
|---|---|---|---|
| Prazo expirado | RP | TIMEOUT_SIA_DC09 | HIGH |
| Heartbeat válido após falha | RP | RESTORED | LOW |

Ambas usam `ALARM_PANEL`, ID da central provisionada, partição default, zona 0 e
`correlation_id=null`. O RP real recebido também permanece como evento original
ACTIVE/LOW na sua zona. Não se inventa um dispositivo por zona ou origem de rede.

## Entrega e alarmes

- Uma notificação de timeout por interrupção, sem republicação periódica normal.
- Retries MQTT preservam UUID e timestamp. Se o retorno chega enquanto o timeout
  aguarda confirmação, o timeout é confirmado antes da restauração.
- Estado limitado por conta: último heartbeat e no máximo duas transições
  pendentes. A fila Paho do processo SIA também tem limite configurável (128).
- Isolamento de contas e overrides de prazo apenas para contas provisionadas.
- A tarefa periódica compartilha o lock com o receptor e é cancelada junto do
  serviço. Esperas de publicação continuam limitadas pelo timeout MQTT.
- O consumer grava um alarme HIGH/UNACKNOWLEDGED na tabela `alarms` existente.
  Seu UUID é o do evento, com inserção idempotente. Nenhuma tabela foi criada.
- O evento continua elegível para R01: a projeção isolada não atribui correlação
  nem altera regras de intrusão. O mesmo incidente pode produzir também um
  alarme R01 CRITICAL quando há câmera desconectada e PIR ativo na janela.
- A lista e o reconhecimento retornam RP também para o alarme sem correlação.
- Retorno da comunicação não reconhece nem limpa alarmes operacionais ou R01.
  O operador continua responsável pelo fluxo de reconhecimento existente.
- Payload de `backend/api/schemas.py` preservado exatamente.

## Configuração e uso

```yaml
integrations:
  sia_dc09:
    mqtt_max_queued_messages: 128
    supervision:
      enabled: true
      heartbeat_mode: "rp"
      timeout_seconds: 60
      check_interval_seconds: 1
      publish_timeout_seconds: 5
      account_timeouts: {}
```

`account_timeouts` permite overrides por ID já provisionado. A CLI permanece
com uma conta por processo. `enabled: false` desliga a supervisão explicitamente;
configurações antigas sem esse bloco mantêm o comportamento anterior.

API/HMI e consumer continuam como processos separados. Reinicie o receptor e o
consumer para carregar o incremento; o consumer produz o alarme persistido:

```powershell
python -m backend.db.consumer
python -m backend.integrations.sia_dc09_listener
```

O smoke usa um prazo reduzido apenas no teste, sem alterar o default da aplicação:

```powershell
python -m tests.smoke_day15
python -m coverage run --source=backend -m unittest discover -s tests
python -m coverage report -m --fail-under=80
python -m flake8 backend tests
```

## Evidências de DoD

- [x] 192 testes Python aprovados, incluindo 15 novos testes de supervisão/alarme.
- [x] Cobertura total 94%; módulo novo de supervisão 99% (meta nova ≥80%).
- [x] Relógio controlado: fronteira exata, salto UTC, renovação, retorno e nova falha.
- [x] Rejeição/replay, falha MQTT, UUID estável, ordem e isolamento por conta.
- [x] Ciclo da tarefa, configuração habilitada/desabilitada e fila MQTT limitada.
- [x] Smoke TCP/AES real em loopback e Mosquitto QoS 1: timeout único e retorno.
- [x] Mesmo evento alimenta a R01 com câmera/PIR sintéticos, sem alterar a regra.
- [x] TimescaleDB real: alarme HIGH idempotente, R01 CRITICAL e reconhecimento
  do alarme isolado com RP preservado. Dados e operador sintéticos removidos
  somente pelos UUIDs gerados no teste.
- [x] Lint, revisão do diff, docstrings, README e plano atualizados.
- [x] Auto-revisão de relógios, ordenação, cancelamento, limites e segredos.

## Limites conhecidos

Estado e deduplicação são locais e voláteis; reiniciar o processo começa uma nova
tolerância. QoS 1 admite redelivery e confirmação ambígua; não há promessa de
exactly-once ou histórico completo de oscilações durante falha prolongada do broker.
O polling e publicações limitadas podem atrasar detecções em relação ao prazo;
o alarme usa o horário em que a falha é detectada pelo receptor.

A política cobre conta e partição default configuradas. Não replica um timeout
em todas as zonas/partições da mansão. Valores de bancada precisam ser alinhados
ao intervalo real da central. O modo RP é uma política do MVP solicitada no
backlog; não é uma afirmação de implementação integral da supervisão DC-09-2026.

A inspeção de alarmes segue o contrato atual da API; não foi feita alteração
visual na HMI. Nenhum equipamento físico ou segredo real foi utilizado. Permanecem
as pendências de homologação SIA/ONVIF e os limites de protocolo do Dia 14.

Próximo item do plano: E7-004, definindo primeiro o encapsulamento Contact ID.

Referência de escopo: [SIA sobre comunicação supervisionada DC-09](https://www.securityindustry.org/2026/03/03/security-industry-association-releases-2026-revision-to-dc-09-standard/).
As decisões locais acima são documentadas como política do PSIM, sem alegar
certificação ou substituir a norma e a homologação do fabricante.
