# Sprint 1 - Dia 8 - Definition of Done

## Escopo entregue

- [x] E4-001 - Motor CEP com janela deslizante por conta e partição.
- [x] E4-005 - Purge automático de eventos fora da janela.
- [x] E4-006 - `correlation_id` compartilhado pelos eventos do incidente.

## Contratos implementados

- Eventos de contas ou partições diferentes nunca compartilham uma janela.
- Eventos atrasados não reabrem uma janela já expirada.
- O evento exatamente no limite da janela permanece elegível.
- Resultados idênticos da mesma regra não são emitidos novamente.
- Correlação e vínculo dos eventos são persistidos na mesma transação.
- O consumidor MQTT persiste o evento antes de avaliar as regras CEP.
- R01 Jammer e R02 Multi-sensor permanecem no escopo do Dia 9.

## Verificações do DoD

- [x] 101 testes automatizados passam.
- [x] Cobertura total de 97% (meta: maior ou igual a 80%).
- [x] `flake8` passa sem erros.
- [x] Funções e classes possuem docstrings.
- [x] Banco real persiste correlação e vincula os eventos.
- [x] Auto-revisão concluída.

As histórias E4-001, E4-005 e E4-006 ficam concluídas após as verificações.
