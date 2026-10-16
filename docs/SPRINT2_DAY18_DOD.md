# Sprint 2 - Dia 18 - Calendário de risco

## Escopo E4-008

Calendário local com modo de risco automático, aplicado à sensibilidade do PIR
simulado e consultável na API/HMI. Política registrada no plano antes de codificar.
Sem comandos para hardware ou análise de imagens. Regras R01/R02 e payload
canônico preservados; nenhum alarme é fabricado apenas por entrar numa janela.

## Política de tempo

- Fuso IANA configurável, default `America/Sao_Paulo`. Instantes precisam incluir
  fuso; UTC é convertido para a hora civil configurada antes da comparação.
- `weekday`: segunda 0 até domingo 6; `hour`: 0–23. Cada entrada cobre a hora
  civil inteira, início inclusivo/fim exclusivo. Domingo 23h termina segunda 00h.
- Datas `YYYY-MM-DD` cobrem o dia civil local inteiro. São datas cadastradas, não
  uma base oficial de feriados nem uma afirmação de validade da pesquisa histórica.
- Coincidência com data e horário usa um único multiplicador. Datas têm precedência
  somente na descrição do motivo. Duplicatas não acumulam efeito.
- Em fusos com horário de verão, duas ocorrências de uma hora repetida são
  elegíveis. Horas civis inexistentes não são inventadas a partir de instantes UTC.
- Configuração inválida falha na inicialização da API/construção do sensor.
  `enabled: false` desativa; bloco ausente preserva a equação legada.
- Configuração carregada por processo; reiniciar API/simulador após editar.

## Sensibilidade no simulador

Equação: `Pd = p_base × (1 − exp(−alpha × |Tcorp − Tamb| × fator))`.
Fator 1 no modo padrão/desativado; no elevado, `pir_alpha_multiplier` (default
1.5, configurável entre 1 e 3). É parâmetro operacional inicial, sem calibração
física ou promessa de ganho percentual de detecção.

Cada chamada recalcula o fator. Não altera `alpha` ou `p_base` armazenados nem
acumula ajustes. Probabilidade continua limitada por `p_base`, inclusive zero
sem contraste térmico. A amostragem mantém o RNG/seed existente. Instância criada
fora da janela pode elevar/reverter durante seu uso sem ser reconstruída.

Os cenários wall_jump/rf_jammer fornecem início + offset original do PIR, mesmo
com aceleração SimPy. Chamadas diretas usam UTC atual ou relógio injetado; não
usam o relógio do navegador. Janelas e evidências R01/R02, prioridades e eventos
dos cenários são mantidos. O calendário não ajusta câmeras, feixe IV ou centrais.

## API e HMI

`GET /api/risco` devolve contrato separado com modo (`STANDARD`, `ELEVATED` ou
`DISABLED`), motivo, fuso, instante UTC/local, fator e escopo `SIMULATOR_PIR`.
Relógio controlado é injetável somente na construção do app para testes; não há
parâmetro HTTP para escolher hora ou elevar o modo.

A HMI mostra modo/motivo/fuso e identifica o ajuste como aplicado ao simulador.
Risco elevado usa atenção por texto, símbolo e cor; não é alarme de invasão.
Consulta inicial e a cada 30s, timeout 5s, confirmação local válida até 35s.
Falha, payload inválido ou confirmação vencida resultam em calendário indisponível.
Uma mudança de modo pode levar até o próximo polling para aparecer na HMI;
o PIR recalcula a política em cada detecção, sem esperar pela interface.

## Evidências de aceite

- [x] 213 testes Python aprovados, incluindo 13 novos testes de calendário/PIR/API.
- [x] Cobertura backend total 94%; calendário, rota de risco e PIR 100%.
- [x] 17 testes frontend aprovados; três novos testes de apresentação do risco.
- [x] `src/lib/risk.js`: linhas, funções e branches 100% pelo relatório V8.
- [x] Fronteiras de hora/dia/ano, UTC, fuso, sobreposição, ano bissexto e DST.
- [x] Validação de configuração, modo desativado/legado, reversão sem acumulação.
- [x] Efeito real na amostragem PIR, zero contraste e probabilidades limitadas.
- [x] Cenários com hora de detecção preservada em velocidades 1 e 10.
- [x] Regressão completa inclui R01/R02 e integrações existentes.
- [x] Lint Python, build Vite, revisão de diff e ausência de segredos.
- [x] Smoke HTTP real com API isolada e relógio controlado: padrão → elevado →
  padrão, dia cadastrado e HMI; falha HTTP simulada resulta em indisponível.
- [x] Desktop 1440px e celular 390px inspecionados, sem overflow horizontal.

```powershell
python -m coverage run --source=backend -m unittest discover -s tests
python -m coverage report -m --fail-under=80
python -m flake8 backend tests
cd frontend
npm test -- --experimental-test-coverage --test-coverage-include=src/lib/risk.js
npm run build
```

Smoke na raiz, com Vite em 5173, Playwright disponível e Edge instalado:

```powershell
node tests/smoke_day18.cjs
```

`PSIM_PLAYWRIGHT_MODULE` pode indicar instalação Playwright existente e
`PSIM_PYTHON` o Python do projeto. O smoke inicia/encerra API isolada em 8001,
sem MQTT nem escrita no banco. O arquivo temporário `tmp/day18/clock.txt`
controla somente esse app de teste. A HMI recebe sua resposta HTTP por interceptação
da rota de risco no navegador; não altera configuração ou relógio de produção.
Capturas desktop/mobile ficam em `tmp/day18`, fora do versionamento.

## Continuidade e limites

E4-008 aceito no recorte local do simulador, sem alegar atuação em equipamentos
físicos ou calibração estatística. Não há sincronização NTP, editor de agenda,
importação de feriados, histórico de mudanças de modo ou novo CEP neste incremento.

Próximo item: integração e fechamento da Sprint 2. Revisar evidências, pendências
e prioridades; planejar integralmente a Sprint 3 antes de executá-la, conforme
seção 11.1 do documento mestre. Esta entrega não fecha a sprint automaticamente.
