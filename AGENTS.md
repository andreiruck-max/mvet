# Manutenção do MVet 1.0
## Arquitetura
Monólito Django 5.2 LTS, PostgreSQL, templates, CSS/JS locais. Código em inglês; interface e documentação em português. `apps/<module>`: models para estrutura, services para regras/transações, selectors para consultas, forms para entrada, views para HTTP. Templates não calculam finanças. Group e Permission do Django representam papéis e permissões.

## Regras invioláveis
- Decimal/NUMERIC: quantidade 4 casas, custo e valorização 6 casas, dinheiro 2 casas.
- Finalidade ausente no Bling exige declaração humana específica e auditada antes da confirmação, inclusive master. Nunca presumir finalidade normal nem mapear tipoNota sem contrato comprovado. Ver ADR 0017.
- Bling é fonte de pré-preenchimento com conferência; não importar custo externo, sobrescrever escolhas locais ou propagar cancelamentos. Preservar vínculos para idempotência mesmo após cancelamento. Ver ADR 0015.
- Venda manual independe de Bling/NF. Master pode salvar rascunhos incompletos e ajustar receita/imposto, mas confirmação preserva estoque e snapshots. Ajuste de receita deve refletir recebível, DRE e exportações. Ver ADR 0016.
- CMV histórico é snapshot. Nunca recalcular venda antiga com custo atual.
- Imposto admite recálculo retroativo autorizado com SaleTaxRevision imutável e auditoria; nunca atualizar imposto histórico diretamente. Ver ADR 0009.
- Operações críticas são atômicas. Lock de produtos por ID crescente antes dos saldos por local.
- Livro de movimentos imutável, com estorno vinculado. Cadastros utilizados são inativados.
- Entrada de estoque não é despesa; transferência não é receita; amortização do principal não é despesa.
- Expense reconhece competência e gera título sem caixa. Classificação histórica só muda com ExpenseRevision e motivo; pagamento não recria despesa. Ver docs/EXPENSES.md e ADR 0012.
- Direção visual aprovada: tabelas de vendas próximas da planilha, caixa por dia/período e compras a pagar. Ver docs/DASHBOARD.md; preservar permissões e normalização.
- Lançar venda NÃO autoriza ver custos, margens, DRE ou bancos. Verificar backend e endpoints.
- Corte 15/09/2026. Sem importação integral da planilha. Aberturas não entram na DRE.
- Nunca versionar dados comerciais, .env real, arquivos de banco ou backups.
- Não editar modelos transacionais livremente no admin.
- Não criar tabelas por mês. Não corrigir schema manualmente.

## Fluxo de alteração
1. Ler documento do domínio, ADRs, serviços e testes afetados.
2. Alterar models e executar `python manage.py makemigrations`. Revisar e versionar migration. Não reescrever migrations já aplicadas.
3. Implementar serviço, autorização backend, formulário e UI.
4. Executar `python manage.py test` contra PostgreSQL, `python manage.py check` e `python manage.py makemigrations --check --dry-run`.
5. Atualizar documento do domínio, backlog e CHANGELOG. Mudança de política exige ADR.
6. Commit pequeno. Só declarar concluído com UI, migrations, testes aprovados e commit remoto.

## Novos módulos
Registrar AppConfig, rotas, permissões, migrations e testes. Adaptadores e /api/v1 usam os mesmos serviços de domínio. Não criar permissões implícitas por nome de grupo.

## Atenção especial
Rever impactos cruzados em custo, arredondamento, locks, idempotência, abertura, cancelamento e competência. SQLite não demonstra concorrência PostgreSQL. docs/BACKLOG.md distingue código entregue de modelo futuro.
