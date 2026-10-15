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
| 3 | E7-005, supervisão de comunicação | Receptor aceito e política por conta | Ausência de RP gera evento canônico de timeout uma vez; retorno restaura supervisão; relógio controlado e smoke com CEP |
| 4 | E7-004, Contact ID | Receptor e identificação do encapsulamento | Definir e documentar o transporte suportado antes de codificar; testes com mensagens conhecidas e smoke. Compatibilidade de central depende do protocolo confirmado |
| 5 | E6-007, mapa 2D | HMI, cadastro local de zonas | Zonas configuráveis, estados com texto/ícone/cor, integração com eventos; testes frontend, build e verificação visual ISA-101 |
| 6 | E4-008, calendário de risco | Política de sensibilidade explícita, CEP e configuração | Datas/horas/fuso e limites definidos antes de editar; testes de borda e regressão das regras R01/R02 |
| 7 | Integração e fechamento | Incrementos anteriores aceitos | Smoke dos caminhos suportados, suíte/lint/build, pendências e backlog revisados; planejar toda a Sprint 3 antes de iniciá-la |

O Dia 14 abrange o subconjunto SIA-DCS e controles NULL. ADM-CID, UDP,
provisionamento/rotação de chaves DC-09-2026 e certificação não são aceites deste
incremento. A cobertura exata de códigos e sintaxe será registrada no seu DoD.

## Capacidade e incertezas

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
