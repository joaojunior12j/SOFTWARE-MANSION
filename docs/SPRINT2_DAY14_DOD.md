# Sprint 2 - Dia 14 - Receptor SIA-DCS TCP

## Escopo do incremento E7-003

Receptor local independente de SIA-DCS sobre TCP, com parser ASCII,
CRC-16/ARC, enquadramento LF/CRC/0LLL/corpo/CR e AES-CBC-128/256.
O [plano de continuidade](SPRINT2_PLAN.md) foi registrado antes da implementação,
conforme a regra acrescentada ao documento mestre.

## Critérios de aceite implementados

- Validar tamanho e CRC antes de interpretar cabeçalhos ou descriptografar.
- Aceitar somente contas provisionadas, com chave por conta no ambiente local.
- Desabilitar texto aberto por padrão; permitir somente por configuração explícita.
- Preservar sequência, receptor e prefixo de linha no ACK.
- Exigir timestamp UTC para mensagens criptografadas e validar a janela temporal.
- Usar IV zero e padding aleatório de prefixo do protocolo, sem PKCS7.
- Reconhecer `#conta|Nri01/BA003` e a forma sem partição `#conta|NBA003`.
- Traduzir BA/BR/TA/TR/RP para o payload canônico sem novos campos.
- Tratar NULL como controle; não fabricar evento RP a partir dele.
- Publicar com MQTT QoS 1 e enviar ACK somente após PUBACK do broker.
- Responder a mensagens criptografadas com ACK também criptografado.
- Reconhecer retransmissões sem republicar dentro do cache local configurado.
- Reutilizar UUID determinístico para eventos com conta/sequência/tempo/dados
  idênticos, inclusive se uma confirmação MQTT falhar e houver retransmissão.
- Limitar tamanho, conexões, espera de leitura, publicação e cache.
- Usar um client ID MQTT próprio para evitar colisão com outros publishers.
- Preservar o schema em `backend/api/schemas.py` exatamente.

## Política de normalização

| Código | Estado canônico | Prioridade |
|---|---|---|
| BA | ACTIVE | CRITICAL |
| BR | RESTORED | LOW |
| TA | TAMPER | HIGH |
| TR | RESTORED | LOW |
| RP | ACTIVE | LOW |

Origem `ALARM_PANEL`; ID físico é o da central provisionada; zona vem dos dados;
partição vem de `ri` ou do default configurado; `correlation_id=null`.
Timestamp ausente em mensagem sem criptografia usa a hora UTC de recebimento.
Uma central com várias zonas continua sendo um único hardware para R02: não
inventar dispositivos físicos a partir de zonas.

## Uso

Defina apenas no `.env` local `SIA_ACCOUNT_ID`, `SIA_DEVICE_ID` e `SIA_AES_KEY`.
A chave deve ter 32 ou 64 dígitos hexadecimais. O exemplo versionado não tem chave.
Conta local limitada a 10 caracteres hexadecimais pelo contrato de persistência.

```powershell
python -m backend.integrations.sia_dc09_listener
python -m tests.smoke_day14
python -m coverage run --source=backend -m unittest discover -s tests
python -m coverage report -m --fail-under=80
python -m flake8 backend tests
```

O serviço roda separadamente de API/frontend. Bind padrão: loopback, porta 5500;
as opções estão em `integrations.sia_dc09`. A classe aceita um registro de contas;
a CLI provisiona uma conta por processo neste incremento.

`cryptography` foi declarada diretamente porque implementa o AES previsto no
documento mestre; `python-jose[cryptography]` continua declarado. O publisher
existente ganhou timeout opcional de PUBACK; chamadas existentes mantêm seu uso.

## Evidências de validação

- [x] 177 testes Python aprovados, incluindo 19 novos testes SIA e timeout MQTT.
- [x] Cobertura total 94%; codec SIA 100% e receptor ≥96% (meta nova ≥80%).
- [x] `flake8 backend tests` e `git diff --check` aprovados.
- [x] Smoke TCP/AES-128/256/ACK/MQTT QoS 1 e rejeições aprovado.
- [x] Docstrings, README, configuração e plano atualizados; auto-revisão feita.
- [x] Schema canônico intacto e revisão sem valores reais de equipamento.

Testes incluem CRC conhecido, exemplo NULL público e vetor público de ACK AES,
além de fixtures sintéticas de BA/BR/TA/TR/RP, AES-128/256, rejeições, relógio,
cache, falha MQTT, fragmentação/concatenação TCP, conexão ociosa e startup.
O smoke usa TCP de loopback real e Mosquitto real em contas sintéticas D014/D015.
Valida os dois tamanhos de chave, ACK criptografado, retransmissão, NULL, rejeição
de CRC/texto aberto e JSON/QoS recebido pelo assinante.

## Auto-revisão e limites

Implementação própria do subconjunto descrito, com referências primárias para
interoperabilidade. Não foram incorporados código Java ou dependências daquela
biblioteca. Vetores de protocolo públicos são identificados nos testes; chaves e
contas desses exemplos não pertencem ao equipamento do usuário.

Frame inválido, desconhecido, antigo ou fora do subconjunto fecha a conexão sem
ACK. NAK/DUH, ADM-CID, dados estendidos/múltiplos eventos, UDP, provisionamento e
rotação de chaves da revisão 2026 não foram implementados. Não alegar conformidade
integral com DC-09-2026. O cache é volátil e limitado; QoS 1 permite retransmissões.
ACK confirma aceitação pelo broker, não a gravação no TimescaleDB. Eventos sem
timestamp não têm identidade durável após reinício. Não há supervisão de ausência
de RP neste incremento: E7-005 é o próximo passo no plano.

O modelo Intelbras ainda não foi confirmado. Não foi utilizada central física;
homologação física de E7-003 e ONVIF permanece pendente. Nenhum IP, usuário,
senha ou chave real foi gravado no repositório.

## Referências

- [Publicação da biblioteca pelo subcomitê SIA](https://www.securityindustry.org/2025/08/26/sia-releases-open-source-library-for-ansi-sia-dc-09-implementation/).
- [Vetores públicos da referência SIA](https://github.com/SIA-Intrusion-Subcommittee/sia-dc-09-library/blob/main/sia-dc-09-parsing/src/test/java/ch/swissdotnet/siadc09/tests/ParsingStandardTest.java).
- [Escopo oficial DC-09-2026](https://www.securityindustry.org/industry-standards/dc-09-2026/).
