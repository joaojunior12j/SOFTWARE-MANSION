# Sprint 1 - Dia 4 - Definition of Done

## Escopo entregue

- [x] E3-006 - Modelo SimPy de câmera IVA com linha virtual finita.
- [x] E3-011 - CLI extensível em `simulate.py`.
- [x] Motor SimPy com registro explícito de cenários.

## Contratos implementados

- A câmera só detecta movimento que cruza lados opostos da linha virtual.
- Cruzamentos fora do segmento configurado não geram detecção.
- Tocar ou permanecer sobre a linha não é contado como cruzamento completo.
- A CLI aceita `--scenario`, `--account`, `--speed` e `--list-scenarios`.
- Cenários ainda não implementados falham explicitamente, sem eventos fictícios.
- O registro será preenchido pelos cenários `wall_jump` e `rf_jammer` nos Dias 6 e 7.

## Verificações do DoD

- [x] 64 testes automatizados passam.
- [x] Cobertura total de 93%; módulos novos entre 98% e 100%.
- [x] `flake8` passa sem erros.
- [x] Funções e classes possuem docstrings.
- [x] CLI e integração com o relógio SimPy validadas por testes.
- [x] Mosquitto e TimescaleDB confirmados como `healthy` no Docker.
- [x] Auto-revisão concluída.

As histórias E3-006 e E3-011 atendem ao escopo e ao DoD do Dia 4.
