# ADR 0055 — Despesas pendentes como visão inicial

Data: 10/11/2026.

A lista operacional de despesas abre no mês de competência atual e em Pendentes, incluindo saldo parcial e excluindo pagamento integral. Limpar filtros retorna ao mesmo padrão. Mês é determinado na consulta, sem datas fixas nem preferência antiga em sessão. Filtros explícitos, inclusive período personalizado vazio para todas as datas, são respeitados; intervalo informado não recebe mês implicitamente. Paginação, pesquisa e exportação usam os mesmos defaults.

Pendentes e vencidas ordenam por vencimento crescente. Destaques com texto e cor distinguem Vencida e Vence hoje; cada linha mostra saldo remanescente e cartões destacam pendente/vencido. Valores são os mesmos do financeiro, inclusive reserva por liquidações futuras. Relatório por competência, DRE e cálculos não mudam. Nenhuma migração ou escrita financeira.
