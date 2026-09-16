# API
Prefixo reservado: /api/v1/. Arquitetura futura chama os mesmos serviços das telas.

## Implementado
GET /api/v1/indicadores/:
- Anônimo: redirecionado ao login por sessão.
- Autenticado sem core.view_dashboard: 403.
- Autorizado: 501 com status=not_implemented, sem dados fictícios.

Não existe API pública de vendas/estoque/financeiro nesta entrega. Não anunciar essas rotas como prontas.

## Convenções futuras
Autorização granular; Decimal serializado como string; datas ISO 8601, timezone explícito; source/external_id e chave idempotente para escritas; paginação; erros por campo. Sessões usam CSRF em mutações. Adapters não alteram saldo diretamente. Autenticação de integração será definida em ADR antes da exposição.

## Busca de produtos implementada
GET `/api/v1/produtos/?q=SKU_OU_NOME`, com sessão autenticada. Aceita operate_stock, operate_sales ou view_costs. Retorna até 20 resultados, cada um com id, label, quantity e kind. Campo cost somente com view_costs. Para kit, quantidade é a disponibilidade global dos componentes e custo é soma da composição atual; saída valida o local escolhido. Consulta vazia retorna lista vazia. Sem acesso: 403; anônimo: redirecionamento para login.
