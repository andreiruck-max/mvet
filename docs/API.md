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

## Fase 3
- `GET /api/v1/vendas/<id>/resultado/`: exige `core.view_costs`; retorna estado, receita, CMV, contribuição e margem percentual individual. Rascunho informa que custo será calculado na confirmação. Sem agregados.
- `GET /api/v1/produtos/?q=...&location=<id>`: parâmetro opcional local limita quantidade disponível (inclui componentes de kits); custo permanece condicionado à permissão.
- UI `/vendas/`: listagem/edição; confirmação e cancelamento exclusivamente POST autenticado com CSRF, mesmos serviços de domínio. API pública de escrita futura.

## Fase 5
`GET /api/v1/financeiro/diario/?start=AAAA-MM-DD&end=AAAA-MM-DD&account=<id>` exige `core.view_finance`. Até 62 dias; retorna quadros por conta e valores sem conta definida, como strings decimais. Parâmetros inválidos: 400; sem permissão: 403. Não expõe saldos a usuário com apenas `operate_finance`.
UI `/financeiro/` usa serviços transacionais e CSRF. POST de liquidação, estorno, cancelamento, realização de transferência e exclusão de conta rejeitam GET. UUID/revisão são obrigatórios para liquidação; integração futura deve usar os mesmos serviços.

## Fase 4
`GET /api/v1/fornecedores/<id>/resumo/`: exige `core.view_purchase_reports`, retorna total, quantidade, ticket médio, última compra e obrigações abertas (valores decimais como strings). Compras em rascunho/canceladas excluídas. Sem permissão: 403.
UI `/compras/` usa serviços para todos os POST com sessão/CSRF; confirmação, recebimento e cancelamento rejeitam GET. Autocomplete de produtos permite compradores, mas custo médio só é retornado com `core.view_costs`.
