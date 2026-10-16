# Sprint 2 - Plano de continuidade

Registro em 15/10/2026, antes do Dia 14, conforme seção 11.1 do documento mestre.
Os Dias 11–13 já foram executados; seus DoDs são as evidências históricas.
Não havia plano consolidado no repositório. Este registro organiza a continuidade
autorizada do backlog, sem transformar o roadmap futuro em compromisso de prazo.

## Meta

Integrar eventos de intrusão ao MVP local, mantendo o contrato canônico, com
adaptadores testáveis, mapa 2D e calendário de risco. Analytics é embarcado na
câmera; o PSIM não analisa imagens. Homologação física permanece separada.

### Limite da versão — decisão do usuário em 15/10/2026

A versão em desenvolvimento integra apenas intrusão (centrais/sensores) e câmeras
IP. Controle de acesso fica fora desta e de todas as demais sprints desta versão,
apenas como possibilidade eventual de atualização futura, sem esforço ou compromisso
agora, para evitar custos de protocolos, leituras e integrações desnecessários.
Reconhecimento facial não é entrega comprometida desta versão nem nova frente.
Analógicas permanecem fora; validação local e homologação física em segundo momento.
Este limite não altera as demais tarefas, sua ordem ou os critérios deste plano;
o fechamento continua exigindo o planejamento integral da sprint seguinte.

## Ordem de execução e aceite

Revisão em 15/10/2026, antes do Dia 16: Dias 14 e 15 concluídos tecnicamente
conforme seus DoDs (192 testes, smoke local e cobertura 94%). Homologação de
equipamentos continua pendente. A ordem das tarefas restantes foi mantida.

Resultado do Dia 16: recorte ADM-CID implementado e validado conforme seu DoD;
200 testes Python, cobertura total 94% e módulo novo 96%, smoke com TCP/MQTT/banco.
Resultado do Dia 17: E6-007 implementado como mapa esquemático com cadastro local,
projeção por dispositivo e smoke MQTT/WebSocket/HMI. Quatorze testes frontend e
build aprovados; evidências no DoD do Dia 17.
Resultado do Dia 18: E4-008 implementado no PIR simulado e indicador API/HMI;
213 testes Python e 17 frontend, cobertura total backend 94% e módulos novos
de calendário/API 100%; build e smoke com relógio controlado aprovados.
Próximo incremento: integração e fechamento da Sprint 2, incluindo plano integral
da Sprint 3. Não há previsão em dias corridos sem dados de capacidade.

| Ordem | Tarefa | Dependências | Aceite e validação |
|---|---|---|---|
| 1, executada | E7-001 e E7-002, ONVIF | MQTT, schema | DoDs dos Dias 11–13; homologação física pendente |
| 2, Dia 14 | E7-003, receptor SIA-DCS TCP ASCII/AES | Referência de protocolo, MQTT, configuração por conta, biblioteca criptográfica prevista no mestre | Frame/CRC/tamanho, timestamp, chave por conta, normalização explícita, ACK após publicação; testes de rejeição, fragmentação e smoke TCP → MQTT |
| 3, Dia 15 | E7-005, supervisão de comunicação | Receptor do Dia 14 aceito | Política registrada abaixo; ausência de RP gera timeout uma vez; retorno restaura supervisão; relógio controlado e smoke TCP/MQTT/CEP |
| 4, Dia 16 | E7-004, Contact ID | Receptor DC-09 dos Dias 14–15 | Subconjunto ADM-CID/TCP definido abaixo; testes de tradução/rejeição/retry, AES e smoke TCP → MQTT → banco. Compatibilidade física pendente |
| 5, Dia 17 executado | E6-007, mapa 2D | HMI, cadastro local de zonas | Zonas configuráveis, estados com texto/ícone/cor, integração com eventos; testes frontend, build e inspeção visual desktop/mobile aprovados conforme DoD |
| 6, Dia 18 executado | E4-008, calendário de risco | Política registrada abaixo, simulador e configuração | Calendário local, ajuste PIR simulado e API/HMI; testes de borda, regressão R01/R02 e smoke aprovados conforme DoD |
| 7 | Integração e fechamento | Incrementos anteriores aceitos | Smoke dos caminhos suportados, suíte/lint/build, pendências e backlog revisados; planejar toda a Sprint 3 antes de iniciá-la |

O Dia 14 abrange o subconjunto SIA-DCS e controles NULL. ADM-CID, UDP,
provisionamento/rotação de chaves DC-09-2026 e certificação não são aceites deste
incremento histórico. Seu DoD registra códigos e sintaxe; ADM-CID foi acrescentado
separadamente no Dia 16, com os limites abaixo.

## Políticas dos incrementos

### Política do Dia 18, registrada antes da implementação

- E4-008: avaliar calendário em `America/Sao_Paulo` usando instantes com fuso.
  `weekday` segue Python (segunda 0, domingo 6). Cada entrada `weekday/hour`
  cobre a hora civil inteira, início inclusivo e fim exclusivo. Datas ISO
  configuradas cobrem o dia local inteiro; sobreposição não acumula multiplicador.
  Datas do YAML são parâmetros locais, sem alegar calendário oficial de feriados.
- Validar fuso IANA, datas, horas, dias e multiplicador ao carregar. Configuração
  inválida deve falhar explicitamente; bloco ausente mantém comportamento legado.
  `enabled: false` permite desativar. Sem consulta externa ou dependência de rede.
- Elevar sensibilidade somente do PIR simulado: multiplicar `alpha` da equação
  existente por 1.5 (configurável entre 1 e 3) em risco elevado, recalculado em
  cada detecção; fora da janela usar alpha base. Preservar `p_base`, aleatoriedade,
  limite da probabilidade e zero contraste térmico. Sem acumular ajustes.
- Cenários usam o instante simulado da detecção (início + offset original),
  independente da aceleração SimPy. Chamadas diretas usam UTC atual ou relógio
  injetado. Testar entrada/saída inclusive entre duas detecções da mesma instância.
- Preservar R01/R02, janelas, número de sensores, prioridade CRITICAL e payload
  canônico. Não reduzir evidência de intrusão nem controlar hardware físico.
- API de consulta `/api/risco` e indicador na HMI com modo, motivo e fuso;
  atualização periódica e falha visível, sem mostrar modo normal a partir de cache
  vencido. Expor explicitamente que o ajuste cobre o simulador.
- Aceite: fronteiras de hora/dia/ano, conversão UTC e horário de verão via IANA,
  desativação, validação, probabilidade e cenários; regressão R01/R02; cobertura
  nova ≥80%, lint/build e smoke API/HMI com relógio controlado. Sem homologação.

### Política do Dia 17, registrada antes da implementação

- E6-007: mapa 2D esquemático, sem escala e sem alegar planta física homologada.
  Cadastro local em `frontend/public/zone-map.json`: conta, partição, zona,
  nome, retângulo em percentuais e lista explícita de dispositivos esperados.
  Inicialmente usar apenas os IDs e zonas do simulador já existente.
- Validar configuração, duplicatas e limites antes de exibir. Exibir erro se
  inválida; nunca substituir silenciosamente por uma mansão fictícia.
- Consumir o JSON canônico do WebSocket existente; sem mudar backend/schema.
  Isolar conta/partição/zona/dispositivo e limitar memória ao cadastro. Ignorar
  eventos desconhecidos, duplicados e fora de ordem por condição/dispositivo.
- Condições independentes: BA/BR para intrusão, TA/TR para tamper; desconexão e
  timeout para comunicação, retorno RP/RESTORED para comunicação. RP/ACTIVE é
  heartbeat e não prova restauração. Não limpar uma condição por outra.
- Zonas sem evidência, dispositivos ainda não observados, conexão indisponível
  ou confirmação vencida não ficam normais. Prazo de confirmação configurável
  (120s de bancada). Anormalidades persistem até restauração da mesma condição;
  reconectar descarta a projeção volátil e exige nova confirmação.
- Mostrar texto, símbolo e cor por estado/prioridade, fundo neutro, seleção por
  mouse/teclado e detalhe com dispositivos, horários e condições. Mapa não
  reconhece/limpa alarmes; lista e diálogo ISA-18.2 existentes permanecem.
- Aceite: testes de isolamento, restauração, prioridade, ordem, configuração e
  perda de feed; build; inspeção visual desktop/mobile e smoke de evento real
  MQTT → WebSocket → indicador. Sem dados físicos ou segredos versionados.

### Política do Dia 16, registrada antes da implementação

- Implementar Contact ID encapsulado em DC-09/TCP (`ADM-CID`/`*ADM-CID`),
  reaproveitando framing, CRC, AES-128/256, limites, timestamp e ACK após MQTT.
  Mesma porta/configuração do receptor existente; nenhum servidor concorrente.
- Sintaxe suportada: `#conta|1130 02 001` (qualificador + código, espaço,
  partição de dois dígitos, espaço, zona de três dígitos). Conta interna deve
  coincidir exatamente com a externa provisionada. Sem campos estendidos.
- 130: BA/ACTIVE/CRITICAL ou BR/RESTORED/LOW; 137: TA/TAMPER/HIGH ou
  TR/RESTORED/LOW, qualificadores 1 e 3 respectivamente. 602 com qualificador 1:
  RP/ACTIVE/LOW, elegível para a supervisão RP do Dia 15. Outros códigos ou
  qualificadores são rejeitados sem ACK, sem publicar ou renovar supervisão.
- Preservar contrato canônico, ID da central e identidade estável em retries
  datados; separar identidade ADM-CID da identidade SIA-DCS. Sem novos campos.
- Referências de fabricante: [Ajax, formato ADM-CID](https://support.ajax.systems/en/manuals/cloud-signaling/)
  e [Reconeyez, equivalência 130/137/602](https://support.reconeyez.com/docs/sia-dc-09-integration).
  São referências de formato e mapeamento; não certificam a implementação.
- Não implementar DTMF telefônico DC-05, handshake analógico, UDP, socket bruto
  proprietário, dados estendidos ou códigos de controle de acesso. Modelo e
  manual da central real continuam necessários para sua homologação.
- Após este incremento: mapa 2D, calendário e integração/fechamento seguem os
  critérios da tabela. Definir cadastro de zonas e política de risco antes das
  respectivas implementações. Não iniciar Sprint 3 sem seu plano integral.

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

## Capacidade e incertezas

Os números de dias identificam incrementos lógicos, não datas ou durações medidas.
Não há dados de capacidade/horas disponíveis para estimar o restante com confiança.
O cálculo anterior de 60 dias a partir de seis sprints não é prazo comprometido;
o roadmap foi explicitamente classificado como intenção na documentação mestre.
Confirmar estimativas no fechamento conforme evidências, sem inventar horas.

Modelo da central, seu encapsulamento Contact ID efetivo e equipamento de bancada
ainda não estão confirmados. O recorte local é ADM-CID/DC-09/TCP, sem prometer
suporte a formatos proprietários. Trabalhar com fixtures sintéticas;
não alegar homologação. Se uma dependência mudar o escopo ou a ordem, atualizar
este plano antes de implementar o trabalho afetado.

## DoD comum

Contrato JSON intacto; testes pertinentes com cobertura nova ≥80%; lint;
integração com componentes adjacentes; docstrings/README/DoD; auto-revisão;
sem segredos reais versionados; commit e push após validação.
