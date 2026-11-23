# ADR 0082 — Consultas de estoque e planejamento por proprietário

Catálogo, seleção de depósito, valores locais, totais e planejamento recebem
company_id. Saldo/custo do catálogo são filtrados por empresa; planejamento
usa movimentos, itens e documentos de compra da mesma empresa. O total de
estoque deriva dos saldos empresariais, incluindo depósitos fora da lista
exibida, em vez de ler Product.value como fonte empresarial.

Consulta secundária é negada explicitamente até a ativação completa; não há
fallback silencioso para empresa 1. SKU/local e fornecedores permanecem
cadastros compartilhados. Estoque mínimo/preço e resumo legado de kits ainda
precisam de política empresarial; não liberar secundária removendo só a trava.

Regressão testa filtros/valores em depósitos distintos e recusa de consulta
secundária. Suíte existente preserva busca SKU, paginação, compras pendentes,
último fornecedor, arredondamento e exports de planejamento. CI PostgreSQL e
Chromium é requisito de integração; não houve validação em produção.
