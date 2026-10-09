# ADR 0034 — Correção de canal e depósito da venda confirmada

O master pode corrigir canal e depósito junto aos valores da venda, com motivo, revisão e chave idempotente. A identidade fiscal, vínculo Bling, produtos, quantidades, consumos originais, CMV e termos tributários históricos permanecem preservados. Não se altera a NF no Bling.

A troca de canal reclassifica os relatórios na data comercial original sem movimento de estoque. O destino deve estar ativo; manter um cadastro já inativo é permitido para não impedir correções monetárias antigas.

A troca de depósito estorna a saída efetiva atual e registra nova saída no destino na data de hoje, dentro da mesma transação e lock do domínio. A cadeia SALE_OUT → SALE_RETURN → SALE_OUT vincula as operações. Componentes e quantidades vêm dos movimentos originais, nunca da composição atual de um kit. A venda passa a apontar para a nova saída; o registro imutável SaleCorrection conserva os IDs anterior/novo e nomes dos cadastros. Cancelamento e recuperação posteriores usam a saída corrigida.

O CMV original não é substituído pelo custo médio atual de outro depósito. O novo depósito usa sua referência local para valorizar o estoque e a diferença do valor histórico fica em StockMovement.cost_variance, reconhecida no resultado da empresa na data da correção (ADR 0029). O formulário esclarece esse comportamento. Troca de depósito não serve como recálculo retroativo do CMV por canal. Sem custo conhecido no destino, a transação inteira falha e orienta cadastrar referência. Saldo negativo continua permitido com referência local. Não há títulos financeiros novos.

Migration 0012 amplia a proteção PostgreSQL somente para correção vinculada ao registro imutável. Alterações de contexto precisam corresponder ao antes/depois; alteração do depósito exige cadeia de operações do mesmo autor, movimentos nos locais correspondentes e quantidades/valores de origem conciliados por produto. Demais snapshots continuam protegidos.

Validação: correção monetária/contextual conjunta, canal isolado, estoque negativo, kit alterado posteriormente, rollback sem referência, destino inativo, revisão antiga, envio repetido, cancelamento/recuperação/nova correção, check_inventory, proteção SQL e navegador.
