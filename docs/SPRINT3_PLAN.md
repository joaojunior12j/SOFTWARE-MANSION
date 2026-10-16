# Sprint 3 — operação autenticada e rastreável

Planejamento integral registrado no fechamento da Sprint 2, em 15/10/2026.
Estado: **planejada, não iniciada**. Base: `34896e2` e fechamento da Sprint 2.
O registro é anterior a qualquer migração, dependência ou implementação desta sprint.

## Meta e capacidade

Permitir que usuários locais autenticados consultem os eventos/incidentes de
intrusão e câmeras IP, que operadores reconheçam alarmes com identidade verificada
e auditoria e que um incidente possa ser consultado em timeline e exportado em PDF.

Capacidade informada pelo usuário: **sem disponibilidade fixa; prazo em aberto**.
Não há horas estimadas ou data final comprometida. Dias 21–28 identificam oito
incrementos sequenciais, com complexidade variável; não são oito dias úteis ou
corridos. Cada incremento termina pelo seu aceite. Dimensionamento poderá ser
revisto com evidência real, registrando a mudança antes do trabalho afetado.
Essa decisão explícita de capacidade prevalece sobre a DoR histórica que pede
uma estimativa numérica: nenhuma estimativa será inventada para preenchê-la.

## Escopo selecionado e limites

- E8-001/E5-009: identidade, JWT, roles e proteção HTTP/WebSocket para uso local.
- E8-002: trilha de auditoria de autenticação, administração local e ACK.
- E5-006/E5-007: histórico filtrado/paginado e consulta do cadastro de dispositivos.
- E6-008/E6-010: timeline e relatório PDF de incidente persistido.
- Administração mínima por CLI local de usuários e vínculo do cadastro legado;
  não há compromisso de painel admin completo ou provisionamento de câmeras.

Somente intrusão/centrais/sensores e câmeras IP. Controle de acesso, RFID/biometria
e reconhecimento facial não recebem tarefas em nenhuma sprint desta versão.
Analytics continua embarcado nas câmeras; não há análise de imagens no PSIM.
Hardware/homologação, câmeras analógicas, 3D, aplicativo móvel, SaaS, TLS MQTT,
criptografia em repouso e requisitos de exclusão de dados não são entregas desta
sprint. Funções não selecionadas não foram canceladas da versão por este plano.

Não prometer “E5 completo”: clear/shelve, buffer/replay de 100 eventos, editor do
mapa, snapshot de estado, câmera/admin ONVIF, R03 e flood permanecem no backlog.
O roadmap histórico “JWT + Admin + Relatórios” é refinado por este recorte.

## Decisões comuns de implementação

### Identidade, sessão e permissões

- Instalação local de uma conta, identificada por `system.account_id`; clientes
  não escolhem a conta por parâmetro. Não implementar tenancy/SaaS.
- Adicionar migrações versionadas, preservando dados existentes. Usuários legados
  sem senha não recebem senha default nem login automático. Bootstrap/admin por
  CLI local com senha solicitada sem eco; sem cadastro público de usuários.
- Hash Argon2id usando biblioteca mantida, mínimo inicial 19 MiB, duas iterações,
  paralelismo 1; salt gerado pela biblioteca. Senhas com 15–128 caracteres, sem
  truncamento, sem registrar senha/hash em logs ou auditoria. Validar custo no
  ambiente local antes de fixar defaults da implementação.
  Essa é uma escolha planejada para credenciais ainda inexistentes: o catálogo
  inicial inclui `passlib[bcrypt]`, mas não há hashes/senhas implementados a migrar.
  Registrar a nova dependência no Dia 21; não alterar dependências neste fechamento.
- JWT HS256 com algoritmo permitido fixo, chave aleatória de pelo menos 32 bytes
  somente em variável de ambiente; validar assinatura, `sub`, `iss`, `aud`,
  `exp`, `iat` e `jti`. TTL inicial 30min, configurável; sem refresh token nesta
  sprint. Esses tempos são política local, não exigência de norma.
- Cookie HttpOnly/SameSite=Strict, Path=/api, Secure habilitado por padrão.
  HTTP sem Secure permitido somente por configuração explícita de desenvolvimento
  em loopback. Não guardar JWT em localStorage, query string ou logs.
- Persistir sessão/revogação por identificador derivado de `jti`; logout revoga,
  usuário desativado ou role alterada passa a valer no servidor, sem confiar em
  role apenas contida no JWT. Segredo ausente/inválido falha explicitamente;
  sem fallback de autenticação desabilitada na aplicação real.
- Login JSON com erro genérico. Limite inicial de cinco falhas em cinco minutos,
  por identidade normalizada e por IP direto, com estado persistido/limitado.
  Não confiar em X-Forwarded-For de cliente sem proxy explicitamente configurado.
- Validar Origin de alterações e do handshake WebSocket por allowlist exata.
  Alterações autenticadas exigem token CSRF associado à sessão em header; token
  obtido por `/api/auth/me` e mantido em memória na HMI. SameSite é complementar.
- `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` formam o
  contrato. Login é a única operação de negócio anônima. Demais endpoints de
  dados e WebSocket exigem sessão; OpenAPI/docs também ficam protegidos na app real.
- WebSocket fecha/rejeita sessão inválida/expirada/revogada; verificar antes de
  entregar eventos e também periodicamente (até 5s), sem aguardar novo evento.
  Revalidar com banco sem bloquear o loop de publicação.

| Operação | OWNER | OPERATOR | ADMIN |
|---|---|---|---|
| Ler alarmes, eventos, dispositivos e risco | Sim | Sim | Sim |
| Ler timeline e baixar PDF | Sim | Sim | Sim |
| Reconhecer alarme | Não | Sim | Sim |

Administração de usuários pela CLI inclui criar, listar, definir senha/role e
desativar; impedir remoção/desativação do último ADMIN ativo. A CLI é um canal
local privilegiado, com ator de auditoria `LOCAL_ADMIN_CLI`, sem inventar usuário.

### Integridade e dados

- `AlarmEvent` permanece exatamente igual; contratos de autenticação/auditoria
  são separados. Produtores ONVIF/SIA/MQTT e cálculo do risco não dependem de JWT.
- ACK mantém contrato atual: o UUID enviado deve coincidir com o usuário da
  sessão, verificado no servidor. A HMI o obtém de `/me` e retira o campo editável
  de UUID. Divergência é rejeitada; identidade nunca vem só do corpo da requisição.
- ACK e registro de auditoria são atômicos na mesma transação; falha no journal
  desfaz a ação. Preservar bloqueio de linha e conflito 409 no segundo ACK.
- Auditoria append-only na API/CLI, com horário UTC do servidor, ator, ação,
  recurso e resultado; sem token, senha, hash ou credenciais de dispositivos.
  Ações negadas/autenticação também geram trilha sem depender de sucesso do ACK.
  Não alegar inviolabilidade contra administrador do banco ou conformidade legal.
- Filtrar eventos sempre por conta configurada. Resolver acesso a alarme pela
  correlação ou evento direto, também limitado à conta. Alarme órfão ou associação
  ambígua não autoriza ação/leitura por adivinhação; retornar não encontrado e
  registrar a pendência. Não atribuir conta a dados legados por suposição.
- Adicionar vínculo explícito de conta ao cadastro de dispositivos. Legados sem
  vínculo ficam pendentes; CLI administrativa permite associá-los explicitamente.
  Consultas nunca expõem `config`, senhas, IPs ou chaves de integração.

### Consulta e relatório

- `GET /api/eventos/historico`: início inclusivo/fim exclusivo com timezone,
  default últimas 24h; máximo 31 dias por consulta. Filtros por partição, zona,
  tipo canônico e correlação. Ordenação estável por timestamp e UUID, com cursor;
  página default 50, máximo 200. SQL parametrizado e índices pertinentes.
- `GET /api/dispositivos`: somente cadastro vinculado à conta, paginado, com
  ID/hardware, tipo, rótulo, partição/zona e ativo. Sem varredura de rede.
- `GET /api/alarmes/{id}/timeline`: eventos canônicos vinculados à correlação
  ou evento direto do alarme isolado, em ordem cronológica estável, paginados.
  Não fabricar detalhes de objeto, vídeo, evidência física ou causas inferidas.
- `GET /api/alarmes/{id}/relatorio.pdf`: mesmo incidente autorizado, horário de
  geração UTC/fuso de exibição explícitos, prioridade, regra, conta/partição,
  eventos e ações auditadas. Suportar alarme correlacionado e comunicação isolada.
  Escapar texto, paginar, gerar em memória/arquivo temporário controlado, sem URLs
  ou imagens externas. Limite de 1000 eventos; acima disso resposta explícita
  pedindo filtro/consulta, nunca relatório silenciosamente truncado.
- Relatório é documento operacional local, sem assinatura digital ou afirmação
  de validade pericial. Exportação gera auditoria sem guardar o conteúdo inteiro.

## Sequência integral de execução

### Dia 21 — S3-01: fundação de identidade e migrações

Dependências: fechamento da Sprint 2, banco local e configuração do projeto.
Adicionar migrações versionadas e testáveis para credenciais/ativação, sessões,
auditoria e vínculo de dispositivos, preservando schema canônico/hypertable.
Implementar hash/validação de senha, configuração de segredo e CLI mínima de
bootstrap. Preparar fixtures autenticadas sem credenciais reais.

Aceite: banco novo e existente migram; reaplicação não perde dados; usuário
legado sem senha não autentica; hash não vaza; senha incorreta falha; bootstrap
não cria usuário/senha padrão; schema e smokes de persistência da Sprint 2 passam.
Validação: testes de migração/hash/CLI e smoke TimescaleDB com limpeza por IDs.

### Dia 22 — S3-02: login, sessão e proteção HTTP/WebSocket

Depende de S3-01. Implementar endpoints auth, JWT/cookie, CSRF/Origin, limitação
de tentativas, revogação, desativação e dependências de identidade. Proteger
endpoints existentes e WebSocket, incluindo fechamento periódico de sessões.

Aceite: assinatura adulterada/algoritmo indevido/expiração/issuer/audience inválidos
rejeitados; anônimo não lê dados; logout/desativação invalidam HTTP/WS; Origem
indevida e mutação sem CSRF falham; cinco falhas acionam limite; segredo não vaza.
Validação: relógio controlado, matriz HTTP/WS, rate limit e smoke com banco/sessão.

### Dia 23 — S3-03: roles e entrada autenticada na HMI

Depende de S3-02. Aplicar matriz OWNER/OPERATOR/ADMIN, origem da identidade no
ACK, login/logout e estado de sessão na HMI; remover UUID editável. Expiração
fecha feed, limpa dados privados da sessão e solicita novo login, sem suprimir
alarmes no banco. Concluir operações administrativas da CLI e proteção do último admin.

Aceite: OWNER não reconhece; OPERATOR/ADMIN reconhecem com identidade real; role
alterada/desativação vale no servidor; UUID forjado falha; token não aparece no
storage/log; mapa, risco e reconexão continuam funcionando após login.
Validação: matriz de permissões, testes frontend/build e smoke visual desktop/mobile.

### Dia 24 — S3-04: auditoria transacional e rastreabilidade

Depende de S3-03. Concluir trilha de login/logout/negativas, administração e ACK;
consulta paginada administrativa `GET /api/auditoria` (somente ADMIN). Usuários
sem essa role veem somente ações pertinentes ao incidente na timeline/relatório.

Aceite: ação/ator/recurso/horário corretos; ACK duplicado gera 409 sem segunda
transição; falha ao gravar auditoria reverte ACK; nenhuma identidade do corpo
substitui sessão; log não contém segredos. Não editar/apagar trilha por HTTP.
Validação: transações reais, concorrência de ACK, falha injetada e matriz de acesso.

### Dia 25 — S3-05: histórico e dispositivos consultáveis

Depende de S3-04. Implementar os dois GETs e seus filtros/cursor/limites conforme
política; aplicar escopo também à lista de alarmes/ACK existentes. Adicionar tela
de histórico paginado e filtros claros; dispositivos permanecem consulta, não setup ONVIF.

Aceite: páginas sem duplicação por empate, limites UTC inclusivo/exclusivo,
partição/zona/tipo/correlação corretos; conta externa, órfãos e dados sensíveis
não vazam; SQL parametrizado; configuração/ID inválido falham explicitamente.
Validação: fixtures de duas contas, fronteiras, paginação real e regressão de alarmes.

### Dia 26 — S3-06: timeline de incidente na HMI

Depende de S3-05. Implementar endpoint/tela de timeline usando alarme selecionado,
incluindo auditoria pertinente e paginação. Navegar a partir da lista/histórico.

Aceite: R01/R02 e alarme isolado mostram somente seus eventos; ordem/horários
legíveis; dados ausentes ficam explícitos; acesso negado não expõe incidente de
outra conta. Não transformar metadata de pessoa/veículo em fato de invasão.
Validação: teste de consulta, ordenação/isolamento e smoke HTTP/HMI com banco real.

### Dia 27 — S3-07: relatório PDF do incidente

Depende de S3-06. Implementar exportação autenticada da mesma visão e botão na
timeline, com limites/contrato acima. Selecionar biblioteca PDF local mantida na
execução e registrar dependência/licença; não usar serviço externo.

Aceite: PDF de R01/R02/alarme isolado, acentos, textos longos, múltiplas páginas,
identidade/horários e dados consistentes com timeline; autorização e auditoria;
limite de eventos explícito; sem busca de URLs ou vazamento de segredos.
Validação: testes de conteúdo/HTTP e renderização/inspeção visual de PDFs reais.

### Dia 28 — S3-08: integração, fechamento e planejamento seguinte

Depende dos sete incrementos aceitos. Atualizar smokes antigos para autenticação
sem retirar suas verificações; executar login → evento MQTT → CEP/banco → HMI →
ACK auditado → histórico/timeline → PDF → logout, com dados sintéticos isolados.

Aceite: suíte/lint/build e cobertura nova ≥80%; regressão integral da Sprint 2;
matriz de roles, expiração/revogação/CSRF e isolamento aprovados; PDFs/desktop/mobile
inspecionados; sem segredos; auto-revisão, DoDs, backlog e README atuais.
Fechar Sprint 3 e planejar integralmente a próxima sprint conforme capacidade e
evidências, sem assumir que o roadmap histórico define seu escopo.

## DoR, mudanças e DoD

Todos os incrementos têm recorte, ordem, dependências, aceite e validação definidos.
Disponibilidade variável foi confirmada pelo usuário; prazo em aberto é decisão
registrada, não bloqueio oculto nem estimativa de oito dias. Dependências de
bibliotecas/migrações são trabalho selecionado, não pré-requisito físico pendente.

Não iniciar um incremento sem aceitar seu predecessor. Evidência nova que altere
política/escopo exige registrar motivo, impacto, aceite e ordem neste plano antes
da implementação; escolhas internas compatíveis não exigem rediscutir o sprint.
Não acumular itens opcionais ou pendências de hardware por iniciativa automática.

DoD comum: testes pertinentes e cobertura nova ≥80%, lint, build quando houver
frontend, teste adjacente com serviços reais, documentação/DoD e auto-revisão;
nenhum segredo versionado; commit/push por incremento conforme autorização vigente.

## Referências técnicas e continuidade

Parâmetros de senha e controles de sessão serão implementados usando bibliotecas,
com estas referências primárias, sem alegar certificação:
[OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html),
[OWASP WebSocket Security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html).

No novo chat: ler primeiro a visão vigente e seção 11.1 do documento mestre,
depois `SPRINT2_CLOSEOUT.md`, `BACKLOG_STATUS.md` e este plano; verificar status
Git e instruções locais. Começar por S3-01/Dia 21 somente quando o usuário pedir
para iniciar. Nenhuma implementação da Sprint 3 foi realizada no fechamento.
