# ADR 0044 — Correção explícita do CMV histórico

Data: 15/10/2026. Status: aceito por solicitação do responsável.

## Decisão
Master pode corrigir custo unitário de itens de venda confirmada mediante prévia obrigatória, motivo, revisão da venda e chave idempotente. Não recalcular com custo atual do estoque. Kits usam custo da unidade comercial completa; composição e consumos históricos não mudam.

Sale.cmv, SaleItem e movimentos continuam imutáveis. SaleCostRevision registra antes/depois por item, total, autor, data, motivo e revisão. Sale.cmv_adjustment armazena somente a diferença acumulada contra o original; effective_cmv soma original e ajuste. Nova correção substitui o valor aplicado, sem acumular o mesmo ajuste novamente. Linhas sem alteração preservam resíduos originais de arredondamento.

Margem individual, API, dashboard, canal, DRE, detalhamento de origem e exportações usam o CMV aplicado na data comercial original. Canceladas ficam fora dos totais. Cancelamento/recuperação preservam o ajuste, mas o estoque continua usando a cadeia original de movimentos. Troca de depósito mantém seu procedimento original e diferenças próprias.

Esta é uma correção gerencial da venda: não altera quantidade, valor, custo médio, diferenças de reposição, financeiro ou tributos. Não corrige automaticamente eventual erro do saldo de estoque atual. A interface deixa essa separação explícita; conciliação do estoque deve ser feita em seu fluxo próprio para evitar duplicar ajustes.

PostgreSQL permite mudar apenas ajuste e revisão com registro correspondente e contexto transacional específico. Revisões de custo não admitem edição/exclusão. A confirmação exige token de prévia assinado para os mesmos valores/autor/venda; revisão rejeita mudanças concorrentes. Permissão ver custos permite consultar histórico, nunca corrigir.
