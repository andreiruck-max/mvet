# API
Prefixo reservado: /api/v1/. Arquitetura futura chama os mesmos serviços das telas.

## Implementado
GET /api/v1/indicadores/ (Fase 7):
- Anônimo: redirecionado ao login por sessão.
- Autenticado sem core.view_dashboard: 403.
- Autorizado: 200 com período, totais de vendas confirmadas e comparativo por canal. Sem bancos/estoque/DRE. Valores Decimal serializados como strings, margem nula quando sem receita. Filtros period/start/end/channel, mesmos das telas, até 366 dias. Inválidos retornam 400; POST retorna 405.

GET `/api/v1/dre/`: exige `core.view_dre`, mesmos filtros. Retorna vendas, despesas por natureza/categoria, resultado financeiro, ebitda/result, `provisional` e `channel_only`. Para canal específico, ebitda/result são null; despesas comuns não são rateadas. Provisório significa resultado parcial, com pendências explícitas. Ver docs/DRE.md e ADR 0013.

As consultas descritas abaixo usam sessão autenticada. API pública de integração/escrita permanece futura.

## Convenções futuras
Autorização granular; Decimal serializado como string; datas ISO 8601, timezone explícito; source/external_id e chave idempotente para escritas; paginação; erros por campo. Sessões usam CSRF em mutações. Adapters não alteram saldo diretamente. Autenticação de integração será definida em ADR antes da exposição.

## Fase 6
`GET /api/v1/despesas/competencia/` exige `core.view_expense_reports`. Filtros: period, start/end (ISO), category, supplier, cost_center, q e status, conforme formulário de despesas. Retorna categories (nome/caminho histórico, natureza, quantidade e valor) e totals por natureza; valores decimais como strings. Canceladas excluídas. Parâmetros inválidos 400; sem permissão 403. UI `/despesas/` usa sessão/CSRF, UUID para criação e revisão para reclassificação; cancelar/parar/classificar somente POST. Ver docs/EXPENSES.md.

## Busca de produtos implementada
GET `/api/v1/produtos/?q=SKU_OU_NOME`, com sessão autenticada. Aceita operate_stock, operate_sales ou view_costs. Retorna até 20 resultados, cada um com id, label, quantity e kind. Campo cost somente com view_costs. Para kit, quantidade é a disponibilidade global dos componentes e custo é soma da composição atual; saída valida o local escolhido. Consulta vazia retorna lista vazia. Sem acesso: 403; anônimo: redirecionamento para login.

## Fase 3
- `GET /api/v1/vendas/<id>/resultado/`: exige `core.view_costs`; retorna estado, receita, CMV, contribuição e margem percentual individual. Rascunho informa que custo será calculado na confirmação. Sem agregados.
- `GET /api/v1/produtos/?q=...&location=<id>`: parâmetro opcional local limita quantidade disponível (inclui componentes de kits); custo permanece condicionado à permissão.
- UI `/vendas/`: listagem/edição; confirmação e cancelamento exclusivamente POST autenticado com CSRF, mesmos serviços de domínio. API pública de escrita futura.

## Fase 5
`GET /api/v1/financeiro/diario/?start=AAAA-MM-DD&end=AAAA-MM-DD&account=<id>` exige `core.view_finance`. Até 366 dias; aceita também period. Retorna quadros por conta e valores sem conta definida, como strings decimais. Parâmetros inválidos: 400; sem permissão: 403. Não expõe saldos a usuário com apenas `operate_finance`. UI apresenta o intervalo em páginas de 14 dias.
UI `/financeiro/` usa serviços transacionais e CSRF. POST de liquidação, estorno, cancelamento, realização de transferência e exclusão de conta rejeitam GET. UUID/revisão são obrigatórios para liquidação; integração futura deve usar os mesmos serviços.

## Fase 4
`GET /api/v1/fornecedores/<id>/resumo/`: exige `core.view_purchase_reports`, retorna total, quantidade, ticket médio, última compra e obrigações abertas (valores decimais como strings). Compras em rascunho/canceladas excluídas. Sem permissão: 403.
UI `/compras/` usa serviços para todos os POST com sessão/CSRF; confirmação, recebimento e cancelamento rejeitam GET. Autocomplete de produtos permite compradores, mas custo médio só é retornado com `core.view_costs`.
