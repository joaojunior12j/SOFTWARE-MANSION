# Sprint 2 - Dia 13 - Transporte de metadados ONVIF

## Escopo e critérios de aceite

Continuação de E7-002: conectar uma fonte RTSP real ao parser de classificação
entregue no Dia 12, com descoberta ONVIF, controle da sessão e remontagem RTP.

- [x] Descoberta de perfis via ONVIF Media1 usando `onvif-zeep` já instalado.
- [x] Seleção somente de perfil com `MetadataConfiguration.Analytics` habilitado.
- [x] Seleção opcional de token; consulta `GetStreamUri` sem alterar a câmera.
- [x] DESCRIBE/SDP seleciona somente `application`, `vnd.onvif.metadata/90000`.
- [x] SETUP negocia RTP/AVP/TCP intercalado; PLAY inicia a sessão.
- [x] Autenticação Digest MD5/SHA-256, com `qop=auth` ou legado sem qop.
- [x] GET_PARAMETER mantém a sessão, respeitando o timeout anunciado.
- [x] TEARDOWN e liberação do socket inclusive em falhas.
- [x] Remontagem usa o marker RTP para fechar XML, não o timestamp RTP.
- [x] Sequência de 16 bits, SSRC, CSRC, extensões e padding são tratados.
- [x] Perda/descontinuidade descarta o documento até o próximo limite seguro.
- [x] Limites de memória para XML, cabeçalhos RTSP e fila de documentos.
- [x] Timeout de leitura/operações SOAP e reconexão com backoff cancelável.
- [x] Documento inválido é descartado; falha no callback encerra a supervisão.
- [x] Host, usuário e senha apenas no ambiente local; URI não aceita credenciais.
- [x] Controles SDP de outra origem e redirecionamentos não são seguidos.
- [x] Logs de falha não incluem endpoints, credenciais ou respostas do servidor.
- [x] JSON canônico, CEP, banco e HMI preservados.

## Correção do Dia 12

O XSD normativo define `tt:MetadataStream`. A grafia `MetaDataStream`, usada
no primeiro parser a partir de exemplos textuais, foi corrigida no parser, na
fixture e nos testes. A enumeração legada `ClassCandidate/Type` usa `Vehical`;
esse valor é normalizado para `Vehicle`. A fixture agora usa a grafia normativa
para o descritor legado. Tipos desconhecidos continuam ignorados.

## Verificação do DoD

- [x] 157 testes Python aprovados (19 novos testes de transporte/supervisão).
- [x] Cobertura total 93%; novos módulos: RTP 100%, RTSP 94%, supervisor 98%.
- [x] `flake8 backend tests` aprovado; docstrings e uso atualizados.
- [x] Smoke com servidor RTSP sintético em socket TCP de loopback: Digest
  verificado pelo servidor, mensagens TCP fragmentadas, RTP/RTCP intercalados,
  remontagem XML e entrega de pessoa/veículo ao callback.
- [x] Smoke verifica TEARDOWN e regressão Profile T com Mosquitto real/QoS 1.
- [x] Corrigida corrida no smoke antigo: aguardar SUBACK antes de publicar e
  verificar o QoS efetivamente recebido.
- [x] Auto-revisão de autenticação, limites, encerramento, contrato e segredos.

```powershell
python -m tests.smoke_day13
python -m coverage run --source=backend -m unittest discover -s tests
python -m coverage report -m --fail-under=80
python -m flake8 backend tests
```

## Uso local

Defina `ONVIF_CAMERA_HOST`, `ONVIF_CAMERA_PORT`, `ONVIF_CAMERA_USERNAME` e
`ONVIF_CAMERA_PASSWORD` somente no `.env` local. Os valores versionados em
`.env.example` são placeholders. Não coloque credenciais na URI RTSP.

```powershell
python -m backend.integrations.onvif_stream --account 1234 --camera-id CAMERA-LOCAL --partition 01 --zone 3
```

`--profile-token` seleciona um perfil específico. Sem ele, seleciona-se o primeiro
perfil com analytics metadata habilitado. O programa imprime observações JSON,
sem convertê-las em alarmes nem persistir atributos de rosto, imagem ou placa.
Timeout, keepalive, limite de XML e backoff ficam em `integrations.onvif`.

## Limites e estado de E7-002

O incremento técnico tem transporte completo para **Media1 + RTSP 1.0 + TCP
intercalado + XML sem compressão**. Não há suporte a Media2 exclusivo, UDP,
gzip/EXI, HTTP tunnel, RTSPS, Basic ou algoritmos Digest diferentes dos declarados.
Só os perfis já habilitados são usados. Encerramento durante uma leitura aguarda
o timeout configurado; TEARDOWN também tem timeout. A reconexão não garante replay
de observações perdidas e não há persistência ou exibição dos metadados na HMI.

E7-002 permanece **pendente de homologação física**, com o incremento testado
contra servidor local sintético. Não foi utilizada câmera real nem foram obtidos
endereço ou credenciais reais. O próximo avanço de backlog pode iniciar E7-003
(SIA DC-09), mantendo a homologação ONVIF como pendência explícita.

## Referências

- [ONVIF Streaming, seções 5.1.2.1.1 e 5.2.2](https://www.onvif.org/specs/stream/ONVIF-Streaming-Spec.pdf).
- [XSD oficial de metadados](https://raw.githubusercontent.com/onvif/specs/development/wsdl/ver10/schema/metadatastream.xsd).
- [RTP, RFC 3550](https://www.rfc-editor.org/rfc/rfc3550).
