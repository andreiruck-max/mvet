# Arquitetura
Monólito modular Django 5.2 LTS + PostgreSQL. Templates e CSS/JS locais evitam dependência de CDN na rede interna. HTMX pode ser incorporado aos fluxos incrementais quando necessário. API separada e SPA não se justificam nesta etapa.

| Módulo | Responsabilidade |
|---|---|
| core | Empresa, corte, auditoria e utilitários |
| accounts | Autenticação, grupos e permissões |
| products | Produtos, marcas, categorias, composição |
| inventory | Movimentos, saldos por local, custo médio |
| sales | Vendas, canais, snapshots, impostos |
| purchases | Fornecedores, compras e recebimento |
| finance | Contas, títulos pagar/receber, liquidação, transferência |
| expenses | Plano de contas, competência e classificação |
| reporting | Dashboard e DRE |
| notifications | Alertas por destinatário e preferências |
| integrations | Adapters e importações futuras |

## Separação
Services validam autorização e executam regras transacionais. Selectors fazem consultas. Views recebem dados validados dos forms. Models e constraints garantem estrutura. Templates não contêm regras financeiras. Admin restrito a cadastros/configurações autorizados; transações exigem serviços.

## Concorrência e custo
Custo médio global por produto. Locais segregam quantidades. Transferência conserva quantidade e valor globais. Produtos bloqueados em ordem crescente antes das alterações. Snapshot por item e componentes consumidos permanece independente de mudanças futuras.

## Operação
Docker Compose, WSGI, banco sem porta publicada. VS Code com ambiente virtual para desenvolvimento. Sessões Django, CSRF, validação de senha, timezone São Paulo e locale pt-br. Repositório não contém dados reais.

Referências: [Django 5.2](https://docs.djangoproject.com/en/5.2/releases/5.2/), [transações](https://docs.djangoproject.com/en/5.2/topics/db/transactions/), [locks](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update).
## Relatórios (Fase 7)
apps/reporting contém forms de período, selectors de agregação Decimal e views read-only. Consome fontes existentes sem novas tabelas. Relatórios gerenciais usam a transação/mutex de domínio para ler múltiplas fontes consistentemente. Dashboards não gravam totais nem inferem competência de movimentação bancária. Apresentação tabular preserva o uso das planilhas; regras em docs/DASHBOARD.md, docs/DRE.md e ADR 0013.
