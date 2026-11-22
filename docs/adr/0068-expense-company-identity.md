# ADR 0068 — Identidade empresarial das despesas

Expense e ExpenseRevision recebem company obrigatória, PROTECT e default constante 1. Constraints transitórias restringem a Mercadovet, coerentemente com títulos e movimentos financeiros. DDL aditivo não atualiza registros históricos nem desativa gatilhos.

Classificações históricas, competência, recorrência e pagamentos permanecem intactos. Plano de contas e regras ainda não são segregados; serviços e formulários continuam em transição. Não habilita outra empresa.

Testes: pagamento conserva proprietário; empresa secundária é rejeitada; migration preserva despesa paga, revisão, títulos, lançamentos e gatilhos, incluindo rejeição de alteração direta de valor. Exigir PostgreSQL e navegador antes do merge. Não aplicar no ambiente 2.0.
