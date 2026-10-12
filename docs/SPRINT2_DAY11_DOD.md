# Sprint 2 - Dia 11 - Definition of Done

## Escopo entregue

- [x] E7-001 (incremento inicial) - Listener ONVIF Profile T via PullPoint.
- [x] Reconhecimento do tópico `RuleEngine/LineDetector/Crossed`.
- [x] Normalização para o payload JSON único do PSIM.
- [x] Publicação no tópico MQTT de analytics da câmera com QoS 1.

## Contratos implementados

- `UtcTime` do evento ONVIF é obrigatório e preservado no payload canônico.
- Cruzamento de linha gera `CAMERA`, `BA`, `ACTIVE` e `CRITICAL`.
- Tópicos ONVIF não suportados são ignorados, sem fabricar eventos.
- `correlation_id` nasce nulo e permanece sob responsabilidade do motor CEP.
- Senha da câmera é lida somente da variável de ambiente indicada.
- IP, usuário e senha reais não são gravados no repositório.
- Timeout e limite do PullPoint ficam na configuração central.

## Verificações do DoD

- [x] Fixture baseada na mensagem ONVIF oficial de cruzamento de linha.
- [x] Testes cobrem tradução, filtragem, timestamp e requisição PullPoint.
- [x] Smoke publica e recebe o payload fixo pelo Mosquitto com QoS 1.
- [x] `onvif-zeep` declarado e validado no ambiente local.
- [x] 123 testes passam com 91% de cobertura (meta: 80%).
- [x] `flake8` e auto-revisão sem erros.

## Limite conhecido

A homologação com uma câmera física depende de IP e credenciais locais do
equipamento. O incremento entrega o caminho completo e testável até o MQTT,
sem incluir qualquer segredo ou endereço real no código.
