# Sprint 2 - Dia 16 - Contact ID sobre DC-09/TCP

## Escopo e revisão do plano

E7-004 implementada no recorte local ADM-CID/DC-09/TCP. A política foi registrada
no plano antes do código. O plano revisado preserva a ordem mapa 2D → calendário
de risco → integração/fechamento, o limite intrusão/câmeras IP e a exigência de
planejar toda a Sprint 3 antes de iniciá-la. Não estima dias corridos sem capacidade.
Homologação física permanece pendente para todas as integrações.

## Transporte e normalização

Reutiliza o receptor do Dia 14: framing DC-09, CRC, tamanho, conta provisionada,
AES-CBC-128/256, janela de timestamp, limites TCP/MQTT, deduplicação e ACK após
publicação QoS 1. Texto aberto exige opt-in existente. Não se implementou um
socket bruto proprietário nem DTMF/handshake de linha telefônica.

Sintaxe exata suportada: `#1234|1130 02 001`, com conta interna igual à externa,
qualificador de um dígito, código de três, espaços simples, partição de dois
dígitos e zona de três. Aceita contas hexadecimais dentro dos limites já existentes
da configuração DC-09 e do banco. Nenhum campo estendido é aceito.

| Contact ID | Código canônico | Estado | Prioridade |
|---|---|---|---|
| 1130 | BA | ACTIVE | CRITICAL |
| 3130 | BR | RESTORED | LOW |
| 1137 | TA | TAMPER | HIGH |
| 3137 | TR | RESTORED | LOW |
| 1602 | RP | ACTIVE | LOW |

Qualificador 6, restauração de 602, códigos desconhecidos, contas divergentes e
variantes de sintaxe são rejeitados sem ACK, publicação ou renovação da supervisão.
A tabela é uma política explícita deste recorte, sem inferir todos os códigos CID.
O código original numérico é normalizado; o JSON persistido contém o código
canônico da tabela. O payload não ganhou campos de protocolo ou de código bruto.

O evento preserva ID da central, partição e zona; não inventa um dispositivo por
zona. UUID de mensagens datadas é determinístico com namespace ADM-CID separado
de SIA-DCS; mensagens sem timestamp mantêm UUID aleatório e cache local limitado.
O teste periódico 1602 alimenta a política RP do Dia 15. Intrusão/tamper e replays
não renovam essa política. Regras CEP e schema não foram alterados.

## Execução

Com os serviços Docker e variáveis SIA locais configurados, iniciar um receptor
(a entrada antiga SIA também aceita ADM-CID):

```powershell
python -m backend.integrations.contact_id_listener
python -m backend.db.consumer
python -m tests.smoke_day16
python -m coverage run --source=backend -m unittest discover -s tests
python -m coverage report -m --fail-under=80
python -m flake8 backend tests
```

As duas entradas CLI usam a mesma porta e não devem ser iniciadas juntas.

## Evidências de aceite

- [x] 200 testes Python aprovados; oito testes novos de Contact ID.
- [x] Cobertura total 94%; módulo novo 96% (meta ≥80%).
- [x] Traduções explícitas, contrato exato, sintaxe/qualificadores rejeitados,
  conta divergente, janela UTC, CRC, AES-128/256 e ACK.
- [x] Retransmissão e falha MQTT: não confirmar antes da publicação; UUID estável.
- [x] Relógio controlado: 1602 renova RP, replay não adia timeout, retorno restaura.
- [x] Smoke com socket TCP real fragmentado/concatenado, AES-128/256, ACKs e retry.
- [x] Mosquitto QoS 1 real: dez eventos, duas contas isoladas e códigos esperados.
- [x] TimescaleDB real: eventos recebidos do broker gravados duas vezes,
  conferência do JSON e idempotência; limpeza somente pelos UUIDs gerados.
- [x] Smoke de regressão do Dia 15: supervisão, alarme HIGH, R01 CRITICAL e
  reconhecimento do operador preservados com MQTT e banco reais.
- [x] Lint, revisão de diff, docstrings, README e plano atualizados.
- [x] Contrato canônico e segredos locais preservados.

## Referências e limites

[Ajax, Cloud Signaling](https://support.ajax.systems/en/manuals/cloud-signaling/)
documenta o exemplo de sintaxe ADM-CID e qualificadores 1/3;
[Reconeyez, SIA DC-09](https://support.reconeyez.com/docs/sia-dc-09-integration)
documenta as equivalências 130/137/602. Implementação Python independente;
nenhum código de biblioteca de terceiros foi copiado.

Não há certificação DC-09, suporte integral Contact ID, UDP, dados estendidos,
provisionamento de chaves ou integração de controle de acesso. A compatibilidade
com a central da mansão depende de modelo/manual e teste de bancada. ACK confirma
publicação MQTT, não persistência no banco; esse fluxo continua assíncrono.
Deduplicação e supervisão são voláteis, com os limites dos Dias 14 e 15.

Próximo item: E6-007, mapa 2D, conforme plano revisado.
