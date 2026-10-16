# Sprint 2 - Plano de continuidade

Registro em 15/10/2026, antes do Dia 14, conforme seção 11.1 do documento mestre.
Os Dias 11–13 já foram executados; seus DoDs são as evidências históricas.
Não havia plano consolidado no repositório. Este registro organiza a continuidade
autorizada do backlog, sem transformar o roadmap futuro em compromisso de prazo.

## Meta

Integrar eventos de intrusão ao MVP local, mantendo o contrato canônico, com
adaptadores testáveis, mapa 2D e calendário de risco. Analytics é embarcado na
câmera; o PSIM não analisa imagens. Homologação física permanece separada.

## Ordem de execução e aceite

| Ordem | Tarefa | Dependências | Aceite e validação |
|---|---|---|---|
| 1, executada | E7-001 e E7-002, ONVIF | MQTT, schema | DoDs dos Dias 11–13; homologação física pendente |
| 2, Dia 14 | E7-003, receptor SIA-DCS TCP ASCII/AES | Referência de protocolo, MQTT, configuração por conta, biblioteca criptográfica prevista no mestre | Frame/CRC/tamanho, timestamp, chave por conta, normalização explícita, ACK após publicação; testes de rejeição, fragmentação e smoke TCP → MQTT |
| 3, Dia 15 | E7-005, supervisão de comunicação | Receptor do Dia 14 aceito | Política registrada abaixo; ausência de RP gera timeout uma vez; retorno restaura supervisão; relógio controlado e smoke TCP/MQTT/CEP |
| 4 | E7-004, Contact ID | Receptor e identificação do encapsulamento | Definir e documentar o transporte suportado antes de codificar; testes com mensagens conhecidas e smoke. Compatibilidade de central depende do protocolo confirmado |
| 5 | E6-007, mapa 2D | HMI, cadastro local de zonas | Zonas configuráveis, estados com texto/ícone/cor, integração com eventos; testes frontend, build e verificação visual ISA-101 |
| 6 | E4-008, calendário de risco | Política de sensibilidade explícita, CEP e configuração | Datas/horas/fuso e limites definidos antes de editar; testes de borda e regressão das regras R01/R02 |
| 7 | Integração e fechamento | Incrementos anteriores aceitos | Smoke dos caminhos suportados, suíte/lint/build, pendências e backlog revisados; planejar toda a Sprint 3 antes de iniciá-la |

O Dia 14 abrange o subconjunto SIA-DCS e controles NULL. ADM-CID, UDP,
provisionamento/rotação de chaves DC-09-2026 e certificação não são aceites deste
incremento. A cobertura exata de códigos e sintaxe será registrada no seu DoD.

## Capacidade e incertezas

### Política do Dia 15, registrada antes da implementação

- Supervisão por conta provisionada, iniciada ao subir o receptor. O primeiro
  prazo também é a tolerância inicial, mesmo sem conexão TCP prévia.
- Default do MVP: RP válido e novo renova a supervisão. `any_valid_message`
  opcional aceita frames suportados válidos, incluindo NULL, sem fabricar RP.
  São políticas locais explícitas; não uma alegação de conformidade DC-09-2026.
- Timeout default 60s, verificação a cada 1s e overrides por conta configuráveis.
  Esses são valores operacionais iniciais de bancada, não tempos homologados.
- Usar relógio monotônico para prazos e UTC local para eventos de supervisão.
  Rejeitados, retransmissões ou timestamps de heartbeat não crescentes não renovam.
- Timeout: `ALARM_PANEL`, `RP`, `TIMEOUT_SIA_DC09`, `HIGH`, zona 0, partição
  configurada. Retorno válido: `RP`, `RESTORED`, `LOW`, mesmo dispositivo/zona.
- Um evento por transição confirmada no MQTT; retries mantêm o mesmo UUID e
  timestamp. Se houver retorno enquanto o timeout aguarda confirmação, manter
  timeout antes da restauração para não deixar uma falha entregue sem retorno.
- Isolar contas, limitar estado por conta e não limpar automaticamente alarmes
  correlacionados da ISA-18.2. O retorno da comunicação não prova fim de invasão.
- Evidência na leitura do consumer: R01/R02 só criam alarmes quando há combinação
  de sensores. Para atender ao alarme de comunicação isolado de E7-005, projetar
  o timeout na tabela `alarms` existente com UUID do evento e prioridade HIGH,
  sem atribuir `correlation_id` ao evento ou impedi-lo de participar da R01.
  O retorno também não limpa automaticamente esse alarme operacional.
- Smoke: receptor AES/TCP real, MQTT QoS 1, timeout/retorno e alimentação da R01
  pelo evento real de supervisão mais câmera/PIR sintéticos; persistência real
  do alarme isolado. Hardware pendente. Essa complementação atende ao mesmo
  escopo E7-005; não muda a ordem, o schema ou as tarefas posteriores do plano.

Os números de dias identificam incrementos lógicos, não datas ou durações medidas.
Não há dados de capacidade/horas disponíveis para estimar o restante com confiança.
O cálculo anterior de 60 dias a partir de seis sprints não é prazo comprometido;
o roadmap foi explicitamente classificado como intenção na documentação mestre.
Confirmar estimativas no fechamento conforme evidências, sem inventar horas.

Modelo da central, encapsulamento Contact ID e equipamento de bancada ainda não
estão confirmados. Trabalhar com fixtures sintéticas e registrar essas pendências;
não alegar homologação. Se uma dependência mudar o escopo ou a ordem, atualizar
este plano antes de implementar o trabalho afetado.

## DoD comum

Contrato JSON intacto; testes pertinentes com cobertura nova ≥80%; lint;
integração com componentes adjacentes; docstrings/README/DoD; auto-revisão;
sem segredos reais versionados; commit e push após validação.
