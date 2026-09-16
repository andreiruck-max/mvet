# ADR 0008 — Datas e cancelamento de vendas
Estado: aceito. Data: 16/09/2026.

A abertura autorizada representa o estoque disponível de desenvolvimento. Não há dados suficientes para reconstruir estoques e custos de cada data passada.

Decisão: separar data comercial (entre corte e hoje) da movimentação física (hoje, ao confirmar). Interface informa que custo corrente será snapshot; nunca apresentar custo corrente como reconstrução histórica. A confirmação usa o mutex do estoque e cria SALE_OUT com vínculos imutáveis de item/componente/movimento.

O estorno comum de estoque restaura snapshots e exige ordem inversa. Essa política não serve para cancelamento comercial após compras/vendas posteriores. SALE_RETURN repõe quantidades e valorização originais, recalculando apenas média atual. Não alterar vendas posteriores. Bloquear estorno genérico de SALE_OUT/SALE_RETURN.

Permissão operacional basta para confirmar/cancelar a venda; execução interna do domínio movimenta estoque sem conceder consultas de custo ou edição geral do estoque ao vendedor. Snapshots só são mostrados com view_costs.

Consequências: cancelamento integral com motivo e auditoria; devolução parcial e ajuste de competência histórica permanecem fora desta etapa. Quando financeiro for implementado, integrar reversão/bloqueio de recebíveis/liquidações antes de permitir cancelamento de vendas com esses vínculos.
