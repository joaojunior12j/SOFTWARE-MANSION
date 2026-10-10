# Sprint 1 - Dia 3 - Definition of Done

## Escopo entregue

- [x] E3-001 - Modelo SimPy do sensor PIR com a equação `Pd(T_amb)`.
- [x] E3-002 - Modelo SimPy do Feixe IV com filtro de duração.
- [x] Parâmetros dos sensores centralizados em `config/config.yaml`.

## Contratos implementados

- O PIR usa `Pd = P_base * (1 - exp(-alpha * |T_corp - T_amb|))`.
- `P_base`, `alpha`, `T_corp` e `T_amb` são obtidos da configuração central.
- O Feixe IV ignora bloqueios abaixo de 50 ms.
- Bloqueios de 50 ms a menos de 100 ms são classificados como suspeitos.
- Bloqueios a partir de 100 ms geram decisão de alarme.
- Os dois modelos avançam o relógio de eventos discretos do SimPy.

## Verificações do DoD

- [x] 50 testes automatizados passam.
- [x] Cobertura total de 90%; módulos novos com 97% e 100%.
- [x] `flake8` passa sem erros.
- [x] Funções e classes possuem docstrings.
- [x] Integração com o relógio SimPy validada por testes.
- [x] Auto-revisão concluída.

As histórias E3-001 e E3-002 atendem ao escopo e ao DoD do Dia 3.
