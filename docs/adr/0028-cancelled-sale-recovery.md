# ADR 0028 — Recuperação auditada de venda cancelada por engano

Uma taxa incorreta levou ao cancelamento de uma venda válida. Excluir a venda ou seu vínculo Bling destruiria histórico e permitiria duplicação. Alterar apenas status deixaria o estoque estornado.

O master pode recuperar uma venda anteriormente confirmada, cancelada e com estorno íntegro, corrigindo somente o campo Taxas. A recuperação é explícita, atômica, idempotente por UUID e protegida por revisão. Preserva data comercial, CMV, itens, consumos originais, imposto e vínculo Bling. Retorna aos resultados na data original. Não reconsulta nem reimporta a NF.

Cria nova saída hoje, reversão do estorno, pelas quantidades e valores históricos. Movimentos antigos continuam imutáveis. A venda aponta para a nova saída, permitindo novo cancelamento pela rotina existente. Saldo insuficiente, valor residual inconsistente, produto/depósito inativo, divergência Bling ou financeiro histórico bloqueiam a operação integralmente. Não cria nem reabre recebíveis.

SaleRecovery é imutável, guarda taxas anterior/nova, usuário, motivo, revisão, cancelamento anterior e os três movimentos. PostgreSQL permite a transição CANCELLED → CONFIRMED apenas vinculada à recuperação correspondente na transação; demais alterações continuam bloqueadas. Substitui a proibição absoluta de recuperação do ADR 0008 e mantém a proteção dos livros e snapshots. A exceção não autoriza edição genérica de venda confirmada nem recuperação de rascunho cancelado.
