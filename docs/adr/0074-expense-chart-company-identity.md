# ADR 0074 — Titularidade do plano de contas e classificação

Status: aceito na transição MVet 3.0.

ChartOfAccount e ClassificationRule recebem company obrigatório com PROTECT,
default Mercadovet e restrição transitória company=1. DDL aditivo conserva IDs,
seed_key, códigos, hierarquia, natureza e regras. Não reclassifica despesas antigas.

Unicidades globais de códigos/seed_key permanecem até contextualização do instalador,
formulários, consultas, relatórios e serviços. Esta etapa não habilita o plano da Agro.
Antes de liberar segunda empresa, unicidades e validação de parent/category devem
incluir empresa, sem reutilização automática das categorias da Mercadovet.

Teste PostgreSQL compara todos os campos do plano hierárquico e regra de classificação
antes/depois da migration e rejeita empresa secundária. Regressão geral inclui DRE,
despesas, edição e classificações históricas congeladas.
