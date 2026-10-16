# Sprint 2 - Dia 17 - Mapa 2D de zonas

## Escopo E6-007

Mapa esquemático integrado à HMI existente, com cadastro local validado, seleção
por teclado/mouse e detalhe por dispositivo. Política registrada antes de
codificar no plano da sprint. Layout inicial corresponde aos cenários locais de
intrusão/câmera IP; não representa planta física homologada ou cobertura real.
Não houve alteração de backend, payload canônico ou regras CEP.

## Cadastro e projeção

`frontend/public/zone-map.json` contém título, prazo e até 100 zonas. Cada zona
define ID/nome, conta, partição, número, geometria percentual e até 32 IDs de
dispositivos. Conta/partição/zona e IDs de zona não se repetem. Coordenadas devem
caber no quadro 0–100; identificadores perigosos e cadastros incompletos são
rejeitados. Erro de leitura/validação aparece na tela, sem layout alternativo falso.

O cadastro inicial usa conta `1234`, partição `01`: muro (zona 1, sísmico e feixe),
PIR (2), câmera IP (3) e central (0), com IDs do simulador em `config/config.yaml`.
Contas e hardware reais exigem edição explícita. Recarregar a página após editar;
gerar novo build ao publicar. Não há editor gráfico, upload de planta ou cadastro
persistido em banco neste incremento.

A projeção em memória aceita somente os endereços/dispositivos cadastrados.
Cada dispositivo possui no máximo três condições independentes:

| Condição | Ativação | Restauração |
|---|---|---|
| Intrusão | BA/SA com ACTIVE | BR com RESTORED |
| Tamper | TAMPER | TR com RESTORED |
| Comunicação | DISCONNECTED ou TIMEOUT_SIA_DC09 | RP com RESTORED |

RP/ACTIVE não cria estado saudável nem limpa falhas. Código desconhecido não
altera a projeção. Uma condição/dispositivo não restaura outra. Mensagens antigas
e com mesmo timestamp da condição são ignoradas, inclusive empates ambíguos;
timestamp inválido ou mais de 30s no futuro também é ignorado. Política de bancada,
sem inventar ordenação de eventos indistinguíveis no mesmo instante.

Prioridade da zona é a pior condição ativa: CRITICAL > HIGH > MEDIUM > LOW.
Anormalidades persistem até restauração explícita, mesmo quando antigas/offline,
acompanhadas do aviso de ausência de confirmação recente. Sem anormalidade,
`Restaurada` exige evidência em todos os dispositivos e conexão disponível.
Caso contrário, `Sem confirmação`. Esse estado não significa proteção normal
homologada. Prazo default 120s, configurável de 1 a 86400s, com atualização a cada
segundo na HMI. É confirmação dos eventos observados, não ping de disponibilidade.

Abrir a página ou reconectar o WebSocket reinicia a projeção; não existe snapshot
histórico. Status MQTT é consultado também a cada 5s. Falha da consulta torna a
conexão indisponível; retorno de MQTT observado também reinicia a projeção para
não reaproveitar uma restauração anterior a uma lacuna no feed. Uma interrupção
menor que o intervalo de consulta pode não ser percebida por essa indicação.

## HMI e alarmes

- Fundo neutro/escuro; prioridades anormais por cor, símbolo e texto. Restaurada
  e sem confirmação em cinza, diferenciadas por texto e símbolo.
- Botões nativos, foco visível, estado selecionado e detalhes associados.
- Detalhes mostram conta/partição/zona, dispositivo, condições e horários.
- Layout conferido em 1440px e 390px, sem rolagem horizontal em celular.
- Sem ACK no mapa: restauração não reconhece nem limpa incidentes persistidos.
  Contadores e diálogo de operador continuam na lista existente.
- Texto da lista vazia ajustado: ausência de incidentes não afirma saúde de todos
  os subsistemas enquanto o mapa contém estados desconhecidos.

## Validação

- [x] 14 testes Node aprovados (dez novos testes do mapa).
- [x] `zoneMap.js`: cobertura V8 de linhas, funções e branches 100%.
- [x] Cadastro inválido/duplicado, geometria, isolamento de conta/partição/zona/ID.
- [x] Restauração independente, prioridade, replay, atraso, falha e confirmação vencida.
- [x] Build Vite aprovado; lint Python e `git diff --check` limpos.
- [x] Smoke navegador Edge headless: MQTT real → API WebSocket real → React.
- [x] Teclado, RP preservando intrusão, BR restaurando, reconexão exigindo confirmação.
- [x] Status MQTT indisponível/retorno simulado no endpoint sem derrubar o broker.
- [x] Cadastro inválido simulado via interceptação; erro visível sem indicadores.
- [x] Capturas desktop/mobile inspecionadas em `tmp/day17` (não versionadas).
- [x] Auto-revisão de limites de memória, isolamento, eventos atrasados e sem segredos.

```powershell
cd frontend
npm test -- --experimental-test-coverage --test-coverage-include=src/lib/zoneMap.js
npm run build
```

Smoke na raiz, com API em 8000, Vite em 5173 e Mosquitto local. Requer Playwright
disponível e Edge instalado; `PSIM_PLAYWRIGHT_MODULE` pode indicar um módulo
Playwright já instalado. `PSIM_PYTHON` permite escolher o Python do projeto:

```powershell
node tests/smoke_day17.cjs
```

O smoke usa IDs públicos do simulador na conta 1234. Não inicia consumer nem
escreve no banco diretamente; um consumer já em execução pode persistir os
eventos sintéticos. Executar somente no ambiente local de testes. Capturas em
`tmp/day17/desktop.png` e `mobile.png`; não há segredos nem hardware físico.

## Continuidade

E6-007 aceita no recorte esquemático local. Planta/dispositivos reais e homologação
permanecem pendentes. Próximo item: E4-008, calendário de risco, definindo antes
datas/fuso, regra de sensibilidade e limites. Sprint 3 segue dependente do
planejamento integral no fechamento da Sprint 2.
