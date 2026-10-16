# Backlog revisado no fechamento da Sprint 2

Registro em 15/10/2026. O documento mestre preserva o catálogo original; este
quadro reconcilia execução e seleção atual, sem transformar intenção em entrega.

| Grupo | Estado após Sprint 2 | Próxima decisão |
|---|---|---|
| E7-001 ONVIF T | Recorte técnico local aceito | Homologação física fora da Sprint 3 |
| E7-002 metadados pessoa/veículo | XML/RTSP/RTP local aceito; observações voláteis | Associação/persistência e hardware não selecionados |
| E7-003 SIA | Subconjunto TCP ASCII/AES aceito | Expansão/certificação não selecionadas |
| E7-004 Contact ID | ADM-CID/DC-09/TCP aceito, não suporte integral a centrais legadas | Manual/modelo e variantes proprietárias pendentes |
| E7-005 supervisão | RP/timeout/retorno e alarme HIGH aceitos | Calibração física/durabilidade não selecionadas |
| E6-007 mapa | Esquema com cadastro local e estado por dispositivo aceito | Planta real, editor e snapshot não selecionados |
| E4-008 calendário | API/HMI e sensibilidade PIR simulado aceitos | Ajuste físico não selecionado |
| E8-001 + E5-009 JWT/roles | Não implementados | Selecionados Sprint 3, Dias 21–23 |
| E8-002 auditoria | Não implementada | Selecionada Sprint 3, Dias 21–24 |
| E5-006 histórico + E5-007 dispositivos | Não implementados | Selecionados Sprint 3, Dia 25 |
| E6-008 timeline | Não implementada | Selecionada Sprint 3, Dia 26 |
| E6-010 PDF | Não implementado | Selecionado Sprint 3, Dia 27 |
| E5-004 clear + E5-005 shelving | Não implementados | Adiados; definir restauração, justificativa e expiração antes de selecionar |
| E5-008 replay/buffer WebSocket | Reconexão cliente existe; replay/buffer não implementados | Não selecionado Sprint 3; não confundir histórico com replay |
| E7-006 admin de câmeras | Não implementado | Não selecionado; CLI de usuários/dispositivos da Sprint 3 não encerra essa história |
| E4-004 R03 energia | Não implementada | Não selecionada; depende de códigos/semântica de energia e cenário |
| E4-007 flood suppression | Não implementada | Não selecionada; deduplicação de transporte não a substitui |
| E3-003/004/005 e novos cenários | Modelos adicionais não entregues nos Dias 11–18 | Repriorizar; evento sísmico sintético não é modelo físico de sensor |
| E6-009 controle visual do simulador | CLI existe; painel não implementado | Não selecionado Sprint 3 |
| E8-003/004/005 | Criptografia em repouso, exclusão e TLS MQTT não entregues | Não selecionados; não alegar conformidade LGPD integral |
| 3D, mobile, SaaS | Roadmap histórico, não escopo deste fechamento | Planejamento futuro, sem datas prometidas |
| Controle de acesso/RFID/biometria | Fora de todas as sprints desta versão | Sem esforço ou compromisso atual |
| Reconhecimento facial/analógicas | Fora do recorte vigente | Sem nova frente nesta versão |

As entregas de fundação, MQTT, PIR/feixe, cenários wall_jump/rf_jammer, R01/R02,
API/HMI de leitura e ACK permanecem com os aceites da Sprint 1. A Sprint 2 não
reescreve sua história nem supõe que todos os itens de cada épico estejam prontos.

Capacidade Sprint 3: sem disponibilidade fixa, prazo em aberto por resposta
explícita do usuário. Seleção/limites/aceites completos em `SPRINT3_PLAN.md`;
pendências não são transferidas automaticamente. Dias indicam incrementos lógicos.
