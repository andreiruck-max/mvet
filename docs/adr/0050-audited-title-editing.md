# 0050 — Edição auditada de obrigações financeiras

Data: 02/11/2026. Status: aceito.

Master pode editar títulos abertos, inclusive liquidados: descrição, favorecido, valor, origem, vencimento, conta prevista, classificação e observação, com motivo obrigatório e versão otimista. Tipo pagar/receber e abertura só mudam em título manual sem qualquer operação bancária e sem vínculo de origem. Cancelados não são editáveis. Valor positivo nunca fica abaixo do principal já liquidado (inclusive baixas futuras). A origem não pode ultrapassar uma baixa ativa. Conta inativa já vinculada pode ser conservada.

A edição não altera lançamentos bancários nem transfere pagamentos entre contas. Corrigir uma baixa exige estorno e novo registro. Tipo e abertura continuam protegidos mesmo após estorno, preservando a interpretação dos movimentos históricos. Chave idempotente, origem, vínculo, criador e principal liquidado não são campos editáveis. FinancialTitleRevision guarda antes/depois, autor, data e motivo; trigger PostgreSQL exige revisão correspondente e bloqueia alterações/exclusões das revisões.

Títulos de despesas redirecionam ao editor auditado de Expense (ADR 0046), que mantém valor, documento e obrigação sincronizados. Não é permitido contornar essa regra pelo serviço de títulos. Acesso direto Editar aparece nas listas de despesas e títulos e na ficha do título.

Em compras e vendas, o valor editado é o da obrigação financeira; documento de origem, estoque, CMV e receita histórica permanecem preservados. Não usar essa ação para alterar itens da nota ou reconhecer descontos/juros no pagamento. A parcela conserva o valor contratual original, mostrado quando diverge. Relatório do fornecedor, parcela, exportação de compras, contas a pagar e caixa usam a obrigação atual. A alteração não registra automaticamente receita/despesa pela diferença; eventual fato econômico deve ser classificado na origem ou na baixa correspondente, sem duplicidade.

Títulos manuais FINANCIAL continuam reconhecidos na DRE pela origem e valor atual, conforme regra já existente. Categorias básicas de títulos não substituem o plano de contas das despesas. Não há edição livre de lançamentos bancários nem admin transacional.
