# MVet 3.0 — Dossiê de implementação multiempresa (handoff)

**Situação:** especificação e auditoria de arquitetura. Este documento NÃO implementa o 3.0 nem autoriza migração de produção.

**Repositório:** andreiruck-max/mvet.
**Código MVet 2.0 de referência:** commit dc18da94a32a77642174ed15a11b1939cc00894d, branch archive/mvet-2.0-2026-11-17.
**Trabalho 3.0:** branch develop/mvet-3.0; PRs incrementais com base nessa branch, nunca diretamente em main.
**Checkpoint real:** C:\Mercadovet\backups\checkpoint_mvet2_20261117_183432, criado em 17/11/2026 às 18h34; SHA-256 verificado, dump restaurado em banco de teste e consultadas core_company (1), auth_user (2), django_migrations (106). Teste de restauração NÃO equivale a todos os testes funcionais. Necessário copiar checkpoint para armazenamento externo criptografado. Não expor .env, dados comerciais nem dumps ao GitHub/chat.

## 0. Ordem explícita ao implementador no próximo chat

Você está trabalhando no MVet 3.0, ERP gerencial Python 3.12/Django 5.2/PostgreSQL 16/Docker Compose, sem substituir a emissão fiscal do Bling.

**Missão:** preservar todas as funcionalidades operacionais existentes do MVet 2.0 para Mercadovet e replicá-las com isolamento de dados para MVet Agro Comercial, além de uma visão consolidada do grupo, com foco máximo no estoque por CNPJ e físico compartilhado. Não considere projeto concluído com mero seletor de empresa na interface. Os controles precisam existir no banco, serviços, permissões, integrações, APIs, relatórios, rotinas assíncronas e testes.

**Segurança de implantação:** NÃO modificar main, o Docker/volume PostgreSQL de produção, o arquivo .env de produção ou as configurações Bling reais durante desenvolvimento. NÃO executar migrations do 3.0 no banco do 2.0. NÃO transformar uma cópia do banco de produção em origem de chamadas externas para Bling. Manter MVet 2.0 operacional até aceitação formal. Não usar comandos de remoção de volumes nem restore sobre o banco ativo.

**Modo de trabalho:** ler AGENTS.md, docs/AI_MAINTENANCE.md, documentos/ADRs afetados e o código real de cada módulo antes de editar. Abrir PR por fase apontando a develop/mvet-3.0, com migrations revisadas, testes PostgreSQL e navegador, evidências e documentação. Não fazer merge na main nem pedir autorização repetida para microetapas. Seguir o plano de fases abaixo. Não afirmar que algo está testado sem executar CI/ambiente adequado.

## 1. Base existente auditada

Foi inspecionada a árvore Git do commit de referência (588 arquivos versionados), com leitura dos contratos centrais, modelos, serviços transacionais, consultas, vistas HTTP, APIs, comandos, migrations de proteção e principais testes. O repositório contém apps para accounts, commissions, core, crm, expenses, finance, integrations, inventory, notifications, products, purchases, reporting e sales; também templates, scripts, JS/CSS e ADRs. A árvore completa foi inventariada, mas a inspeção não significa execução linha a linha de todos os 588 arquivos nem homologação do banco real.

| Módulo | Código crítico | Funcionalidade a preservar |
|---|---|---|
| Empresas, acesso e UI | apps/core/models.py, services.py, navigation.py; apps/accounts/access.py, backends.py, permissions.py; templates/base.html | Configuração, corte, master, regras explícitas por usuário, auditoria, menus, modais, preferências |
| Produto e precificação | apps/products/models.py, services.py, pricing.py | SKU global, categoria, marca, kit virtual, inativação, preço fixo/markup |
| Estoque | apps/inventory/models.py, services.py, selectors.py, counting.py, reconciliation.py, importing.py, planning.py, planning_exports.py | Estoque/local, custo médio por depósito, livro imutável, venda negativa, reposição, transferência, fracionamento, kit, contagem, Excel, planejamento e exportação |
| Vendas | apps/sales/models.py, services.py, taxes.py, corrections.py, cost_corrections.py, recovery.py, installments.py | Rascunho, confirmação, baixa, cancelamento/recuperação, NF, impostos, comissão, fretes, CMV congelado e correções auditadas |
| Compras | apps/purchases/models.py, services.py, views.py, forms.py | Fornecedor, rascunho, pedido, recebimento, bonificação, itens sem estoque, descontos, frete interno/externo, rateio e parcelas |
| Financeiro | apps/finance/models.py, services.py, selectors.py, editing.py, due_payments.py | Contas, títulos, saldos, realizado/projetado, transferências, baixa parcial/futura, vencimentos e estorno |
| Despesas | apps/expenses/models.py, services.py, editing.py, bulk.py, chart.py | Plano hierárquico, competência, recorrência, edição auditada, lote, separação caixa/DRE |
| Comissões | apps/commissions/models.py, services.py, selectors.py | Comissionado, parcelas, repasses por recebimento, custo na venda, base produtos e PARTNER_PROFIT, compensação de reversão |
| CRM | apps/crm/models.py, services.py, intake.py, importing.py, selectors.py | Carteira, segmentos, importação, tarefas, recorrência, atividades e permissões |
| Bling | apps/integrations/bling.py, models.py, services.py, purchase_services.py, scheduling.py, bank_services.py, stock_comparison.py | OAuth, notas vendas/compras, revisão, IDs externos, produtos, estoque/preço, extratos, worker |
| Indicadores e documentos | apps/reporting/selectors.py, datasets.py, evolution.py, drilldown.py, exports.py, views.py, files.py; static e templates | Dashboard, DRE, evolução, venda por canal, Excel/PDF, caixa, projeções e drill-down |
| Notificações | apps/notifications/models.py, services.py, selectors.py | Alertas de estoque, margem, vencimento, backup e leitura por usuário |
| Implantação e proteção | docker-compose.yml, scripts/update_windows.ps1, backup.sh, test_restore.sh; .github/workflows/tests.yml | Windows updater com backup/teste, worker Docker, CI PostgreSQL e navegador |

**Observação de fonte:** alguns README/ADRs preservam descrições de etapas históricas e podem estar defasados (ex.: estoque negativo e integração Bling). Para comportamento efetivamente implementado, prevalecem models/services/migrations/tests do commit, verificados contra os ADRs mais recentes.

## 2. Decisões de negócio fixas

1. Uma única instalação MVet 3.0 para o grupo, múltiplos CNPJs com isolamento transacional rigoroso.
2. Mercadovet continua empresa principal administrativa; não tem monopólio do estoque.
3. MVet Agro Comercial (razão MVET PRODUTOS AGROVETERINÁRIOS LTDA) vende, compra de terceiros, mantém custos/estoques/contas próprios e pode vender à Mercadovet.
4. Mercadovet também vende/comprará de terceiros e poderá comprar da MVet Agro. Abastecimento interempresa é **bidirecional**.
5. O **SKU e descrição do item são compartilhados** no catálogo do grupo; saldos, custos médios, preços, mínimos, regras e IDs externos são por empresa. Marcas/categorias e kits podem ser referências globais, com configurações comerciais próprias por empresa.
6. Os depósitos representam **locais físicos** compartilháveis: barracão, Full e demais locais reais. A propriedade de cada quantidade é atribuída à empresa. Não duplicar a quantidade física quando ocorrer só mudança de proprietário.
7. A empresa que vende ao cliente pode registrar saldo individual negativo mesmo se a outra empresa for proprietária das unidades despachadas. Após venda interempresa documentada, os saldos por CNPJ são regularizados sem segunda baixa física.
8. Compras próprias de qualquer empresa elevam seu saldo individual e o físico quando mercadoria realmente entra; compras interempresas em depósito compartilhado não elevam físico.
9. Cada empresa possui uma CONTA INDEPENDENTE no Bling, com autenticação OAuth, tokens, notas fiscais, pedidos, compras, depósitos, produtos e bancos próprios. A disponibilidade comercial publicada por cada conta/marketplace é de responsabilidade daquela configuração externa. O MVet produz a visão física consolidada do grupo internamente; nunca assumir que contas Bling independentes compartilham automaticamente saldos ou a funcionalidade Bling Multiempresas.
10. Para operação interempresa, o fornecedor forma preço a partir de SEU custo próprio e de imposto parametrizado; margem de contribuição padrão zero, ajustável de forma explícita. Referência ilustrativa: preço = CMV / (1 - alíquota - margem), para uma fórmula percentual compatível com a base tributária configurada. Não assumir 8% real para todo produto.
11. Pedido de venda interempresa enviado ao Bling da **fornecedora**, nas duas direções, mediante ação explícita e rastreável. Emissão de NF continua no Bling. Vincular pedido e documentos posteriores à operação interna.
12. A **compradora** registra contas a pagar; não criar contas a receber operacionais automáticas na fornecedora, conforme decisão vigente, mas registrar a receita e conciliar entradas/saídas bancárias. Não compensar pagamentos automaticamente entre CNPJs.
13. Nas telas, alternar Mercadovet, MVet Agro e Grupo. Modo Grupo é consulta agregada/consolidada, não origem de operações. Nenhum dado individual é alterado por alternar o filtro.
14. Consolidação de resultados elimina receitas, CMV e lucro interno não realizado, quando aplicável; conserva custos e tributos efetivamente incorridos por empresas perante terceiros. Visões individual, agregado bruto e consolidado com eliminações devem ser distinguíveis.
15. O usuário determinou fluxo operacional de emissão pela empresa vendedora, saldo individual negativo temporário e compra posterior da outra empresa. Registrar a decisão; não inserir bloqueios artificiais no ERP. O tratamento da documentação no Bling é responsabilidade operacional externa ao ERP.
16. Todo histórico atual da Mercadovet deve permanecer íntegro, com mesmo ID, dados, custo/snapshot, parcelamento, comissão, movimentações e auditabilidade.

## 3. Arquitetura de estoque — PRIMEIRA PRIORIDADE

### 3.1. Livro único por empresa-proprietária e local

**Proposta técnica:** evolução aditiva do livro atual para cada linha ter empresa proprietária, SKU, local, quantidade assinada, valor assinado, custo médio histórico e operação de origem. Um evento interempresa poderá conter duas pernas por empresa (+compradora / -fornecedora) no mesmo depósito e no mesmo produto, com quantidade física líquida zero.

- Saldo empresarial: soma de movimentos por (empresa, produto, local).
- Saldo físico consolidado/teórico: soma algébrica dos saldos de todas as empresas para (produto, local), ou projeção materializada verificável do mesmo livro; sem gerar estoque em dobro.
- Custo médio: SEMPRE por (empresa, produto, local), respeitando Decimal quantidade 4 casas e custo/valor 6 casas. Jamais usar Product.average_cost global para formar CMV de CNPJ específico.
- Product.quantity/value/average_cost existentes exigem plano explícito de compatibilidade: projeção consolidada/informativa, não fonte de CMV por empresa; manter comportamento legado em fase de transição e proibir leitura acidental como custo do proprietário.
- A empresa não pode usar um saldo próprio positivo em um local se a soma física disponível do local é insuficiente sem registrar exceção de venda negativa conforme política existente. Mostrar diferença entre saldo individual, físico agregado, reservado e disponibilidade Bling, sem confundir propriedade com quantidade existente.
- Contagem física altera físico UMA vez e exige identificação/auditoria da empresa que assumirá a diferença; nunca ajustar automaticamente ambos os CNPJs para a mesma diferença.
- Transferir fisicamente entre depósitos preserva a empresa proprietária. Transferência interempresa no mesmo depósito preserva o físico. Se forem simultâneas, registrar ambos efeitos explicitamente, sem dupla contagem.
- Kits virtuais consomem componentes de estoque, por local e empresa, com snapshots de cada componente.
- Reversão deve restabelecer as mesmas pernas, custo, fonte e vínculo; operação idempotente e com controle cronológico.
- Revisar seriamente locking: apps/inventory/services.py usa pg_advisory_xact_lock(763820102), locks de Product em ordem crescente e StockBalance; ampliar ordenação para (empresa, SKU, local) e evitar deadlock/oversell.
- Não trocar o livro imutável por alterações de saldo sem movimentos. Adaptar apps/inventory/management/commands/check_inventory.py para validar saldos por empresa, físico do grupo e reversões.

### 3.2. Exemplo obrigatório A: Mercadovet fornece à MVet Agro

Inicial: Mercadovet +10, MVet Agro 0, físico grupo 10 unidades do SKU X no mesmo depósito.
MVet Agro vende 2 ao consumidor: Mercadovet +10, MVet Agro -2, físico grupo 8.
Mercadovet vende/documenta 2 para MVet Agro: Mercadovet +8, MVet Agro 0, físico grupo continua 8.
NÃO produzir nova entrada física e NÃO dar segunda baixa ao consumidor.

### 3.3. Exemplo obrigatório B: MVet Agro fornece à Mercadovet

Inicial: Mercadovet 0, MVet Agro +5, físico grupo 5.
Mercadovet vende 3: Mercadovet -3, MVet Agro +5, físico grupo 2.
MVet Agro fornece 3: Mercadovet 0, MVet Agro +2, físico grupo continua 2.

### 3.4. Exemplo obrigatório C: compra externa própria da MVet Agro

Inicial: Mercadovet +2, MVet Agro 0, físico 2.
Compra externa MVet Agro, recebimento físico +5: Mercadovet +2, MVet Agro +5, físico 7. Preço e custo da compra atualizam apenas o custo da MVet Agro.

### 3.5. Origem das unidades / dívida interempresa persistente

Não gerar necessidade de compra apenas porque saldo atual está negativo! Registrar a alocação de origem de cada venda ou consumo de componente (venda/linha/componente, empresa vendedora, empresa proprietária abastecedora, SKU, depósito, quantidade, custo provisório, pendência, documentos e estado). Compras externas posteriores não quitam implicitamente obrigação gerada por venda que consumiu estoque pertencente à outra empresa. Fornecimento entre empresas baixa a pendência vinculada, inclusive parcial, e impede quitação em duplicidade.

Quando o CNPJ vendedor ainda não tem custo histórico próprio, não exigir que o usuário lance uma correção fictícia de custo para viabilizar a primeira venda. Definir orçamento/custo provisório a partir de cotação interna ou outro valor explícito auditado, com origem marcada como provisória. Após compra/NF real, conciliar custo definitivo com documentação e rever a DRE sem reescrever CMV original.

**Risco de duplicidade gerencial:** apps/inventory/services.py já lança StockMovement.cost_variance quando entrada cobre saldo negativo; apps/sales/cost_corrections.py admite Sale.cmv_adjustment. Reconciliar CMV provisório -> definitivo com UM mecanismo econômico líquido, sem lançar a mesma diferença tanto em cost_variance na DRE quanto no ajuste do CMV. Manter livro e snapshot imutáveis; registrar revisões explícitas e identificadas.

### 3.6. Reconciliação com Bling

Os depósitos do Bling e locais físicos do MVet não são necessariamente a mesma entidade. Manter mapeamento explícito por conexão/depósito/local/empresa; o estoque virtual compartilhado em marketplaces é comercial e não deve virar entrada física. Conferência, prévia e correção de preços/saldos devem operar no CNPJ correto. Por padrão, comparar e alertar; NÃO escrever ajustes de estoque no Bling sem comando explícito do master e proteção contra operação ambígua. Tratar Full separadamente pela localização física.

## 4. Mudanças de modelo e restrições

| Entidade atual | Modificação recomendada |
|---|---|
| core.Company | Remover CheckConstraint single_company, manter empresa pk=1 como Mercadovet; criar CNPJ único, fantasia, ativa, principal, corte/configuração próprios. |
| accounts.AccessPolicy + auth | Preservar capacidades existentes; criar vínculo UserCompanyAccess com permissões por empresa e leitura consolidada autorizada. Superusuário controla o grupo; ausência de acesso explícito = negação. |
| products.Product | Catálogo SKU global sem duplicação; custo/estoque/preço por CNPJ via CompanyProductPolicy/CompanyStockBalance. Separar preço fixo/markup/mínimos por empresa. |
| inventory.StockLocation | Local físico global, com vínculo de uso/acesso das empresas. Não criar um depósito fictício para cada empresa se o espaço real é compartilhado. |
| inventory.StockBalance / StockMovement / StockOperation | Empresa nos saldos e pernas do livro, novos identificadores/vínculos interempresa, unicidade (empresa,produto,local); histórico Mercadovet backfilled, reversões e variâncias intactas. |
| sales.Sale / SaleItem / SaleConsumption | Empresa vendedora obrigatória; unicidade (empresa,número,série) para NF não vazia; confirmar/cancelar/recuperar/corrigir só em empresa selecionada; mapeamento de origem de componentes. |
| sales.SalesChannel / TaxRule | Canal, payee padrão e tributação por empresa; nomes iguais permitidos entre CNPJs. |
| purchases.Purchase / PurchaseInstallment | Empresa compradora; unicidade documental levando empresa em conta; compras próprias e de outra empresa tratadas no mesmo motor de custos, mas com origem interempresa sinalizada. |
| purchases.Supplier | Cadastro de fornecedores possivelmente compartilhável no grupo; NÃO deixar uma compra trocar de empresa por fornecedor; documentos e filtros da compra sempre por empresa. |
| finance.FinancialAccount / FinancialTitle / FinancialOperation / FinancialEntry | Titularidade por empresa, validação de que título/conta/lançamento têm CNPJ coerente, nomes de contas repetíveis entre CNPJs; transferências bancárias dentro de empresa preservam livro, pagamentos entre empresas são transações independentes vinculadas. |
| expenses.Expense / ChartOfAccount / ClassificationRule | Despesas/categorias/regras por empresa ou política de plano global com mapeamento; códigos de conta iguais em empresas distintas; DRE competência individual e consolidada. |
| commissions.Payee / Plan / Entry / Payment | Comissão vinculada à venda e CNPJ; planos PARTNER_PROFIT, liberações, pagamentos e compensações preservados; a mesma pessoa pode vender em mais de um CNPJ sem mesclar liquidações. |
| crm.Contact / Interaction / Intake / regras | Contatos/atividades com CNPJ de carteira; visão grupo apenas para autorizados; definir política explícita de compartilhamento, não vazar contatos via unicidade global de telefone/e-mail. |
| notifications.Notification | Chave de condição inclui empresa, exceto alertas verdadeiramente de grupo; leitura e links respeitam empresa/permissão. |
| integrations.BlingConnection | Remover single_bling_connection; uma conexão OAuth por CNPJ, issuer imutável, tokens e refresh independentes; adaptar BLING_ISSUER_CNPJ de ambiente singleton. |
| integrations.BlingSchedule / ReviewDefaults / ComparisonCache | Scheduler por (empresa,tipo); defaults e caches por empresa/usuário/conexão; nenhuma consulta de empresa A alimenta cache B. |
| integrations.InvoiceImport / PurchaseInvoiceImport / ProductAlias | Preservar unicidades por conexão existentes, conferir vínculo de conexão à empresa da venda/compra; chave NF-e global continua única; criar mapeamento external_product_id ↔ SKU por conexão. |
| integrations.BlingBankAccount / Link / Run / Staging / Entry / Day | Extrato isolado por conexão e conta da MESMA empresa. Não propagar saldos Bling para bancos MVet automaticamente. |
| reporting / exports / dashboard | company_scope obrigatório. Modo grupo bruto e consolidado, com eliminações; preservar granularidade e permissão de custos/bancos. |

### Triggers PostgreSQL: MIGRAÇÃO NÃO É UPDATE LIVRE

O MVet 2.0 tem gatilhos de imutabilidade em inventory_stockoperation, inventory_stockmovement, sales_sale, sales_saleitem, finance_financialentry, finance_financialoperation, finance_financialtitle, despesas e comissões. Referências: apps/inventory/migrations/0002_immutable_ledger.py; apps/sales/migrations/0002_protect_history.py e 0012/0014; apps/finance/migrations/0003_ledger_protection.py e 0005; apps/purchases/migrations/0004; apps/commissions/migrations/0003; apps/expenses/migrations/0002. Um RunPython que faça UPDATE em linhas históricas protegidas pode falhar ou, pior, exigir desativação insegura de triggers.

Estratégia: primeiro adicionar colunas por DDL com default CONSTANTE Mercadovet (id 1) onde tecnicamente viável e verificado no PostgreSQL, sem UPDATE de linha; remover defaults de novos registros depois; ampliar constraints/guards; testar plano numa cópia restaurada e consultar pg_trigger/pg_constraint. Nunca desabilitar genericamente triggers em produção, reescrever migrations antigas, ou recriar IDs. Para modelos com regras complexas, fazer migrações menores controladas e verificar antes/depois cada soma e contagem.

### Hardcodes e unicidades globais a eliminar

- core.Company tem constraint id=1 e services/selectors consultam pk=1.
- apps/products/pricing.py; inventory/services.py, selectors.py; sales/services.py; purchases/services.py; finance/services.py; expenses/services.py, editing.py; reporting/datasets.py, evolution.py, exports.py; integrations/stock_comparison.py, purchase_views.py; setups e telas consultam Company pk=1.
- BlingConnection obriga id=1; apps/integrations/bling.py e banco/worker usam pk=1; config.BLING_ISSUER_CNPJ é único.
- BlingSchedule.kind é único globalmente; CommissionSettings, ReviewDefaults, AlertConfiguration são singletons; decidir se configuração é por empresa ou grupo e preservar defaults.
- Unicidades hoje globais em Product.sku (DEVE continuar global), StockLocation.name (pode continuar global físico), FinancialAccount.name (MUDAR para empresa + nome), Sale nota número/série (MUDAR por empresa), Purchase supplier/documento/série (MUDAR por empresa), SalesChannel.name (MUDAR), ChartOfAccount.code (avaliar plano por empresa), CRM phone/email (definir política), Notification(kind,entity_id) (MUDAR para empresa + tipo + entidade).
- As views e formulários atualmente permitem diversos get_object_or_404(Model, pk=...) e querysets globais. A migração exige filtros por CNPJ em TODAS rotas, serviços, exports, pesquisa SKU, endpoints JSON, popups, jobs e FKs enviadas por POST, não apenas filtros na listagem.

## 5. Bling e operação interempresa

### 5.1. Uma conta Bling INDEPENDENTE por CNPJ — contrato obrigatório (17/11/2026)

**Não usar conta única, token compartilhado ou apenas filtrar uma conta Bling pela empresa.** Mercadovet tem sua conta Bling; MVet Agro tem OUTRA conta Bling. A conexão é a identidade empresarial externa, não um seletor visual.

| Controle | Bling Mercadovet | Bling MVet Agro |
|---|---|---|
| CNPJ emitente e conta Bling | Mercadovet | MVet Agro |
| Autorização OAuth | Login/autorização próprios | Login/autorização próprios |
| Access token e refresh token | Secret e ciclo de rotação próprios | Secret e ciclo de rotação próprios |
| Notas de venda/compra, pedidos e NF-e | Consulta e identidade próprios | Consulta e identidade próprios |
| Produtos, depósitos, IDs externos e preços | Mapeamento por conexão | Mapeamento por conexão |
| Bancos, extratos, saldo de abertura e conciliação | Contas financeiras Mercadovet | Contas financeiras MVet Agro |
| Rotinas automáticas, filas, páginas, cursores e erros | Independentes | Independentes |
| Permissões e logs de execução | Escopo empresarial | Escopo empresarial |

**API e dados:** todos os métodos públicos do adaptador devem receber um objeto `BlingConnection` (ou `company` que seja resolvido e validado para a conexão correta), nunca usar `pk=1`, token global ou company inferida da NF. Uma conexão pertence de forma imutável a um CNPJ; `UNIQUE(company)` e `UNIQUE(issuer)` se a política for uma conexão por empresa; nunca permitir que dois CNPJs usem a mesma conexão. Preferir FK `BlingConnection.company` com `OneToOneField` e `issuer == company.cnpj`, com verificação no backend. O produto SKU 100 pode mapear para IDs externos distintos em cada conta.

**OAuth:** a tela administrativa permite "Autorizar Bling Mercadovet" e "Autorizar Bling MVet Agro" separadamente, com status por empresa. O `state` do OAuth deve associar, de forma íntegra e de uso único, usuário, empresa e tentativa; o callback salva o token APENAS na conexão originadora. Reautorizar, expirar ou desconectar MVet Agro jamais invalida a Mercadovet. Um mesmo aplicativo integrador OAuth pode, se suportado pela configuração do Bling, autorizar duas contas distintas; não confundir `CLIENT_ID/SECRET` do aplicativo com os tokens individuais de cada conta. Prever credenciais de aplicativo por conexão se forem necessárias em homologação, sem fixar essas credenciais no código e sem publicar segredos.

**Operação:** filas de notas de venda e compra, agendamento `(company, kind)`, `ImportRun`, `ReviewDefaults`, `ComparisonCache`, aliases, estoque/preço, consulta por série/número, movimentações financeiras, status e histórico ficam isolados por conexão. Worker processa cada conta com escopo persistido e erro de uma conta não suspende a outra. IDs de pedidos/produtos do Bling nunca são considerados globalmente únicos: usar `(connection, external_id)`.

**Segurança:** chamadas de leitura/escrita conferem no serviço (não somente na view) que empresa selecionada = empresa da conexão = empresa da operação. Não aceitar `connection_id` arbitrário em POST de funcionário. Nenhuma movimentação no Bling de uma conta poderá ocorrer com token da outra. Na visão Grupo, agregar leituras internas já importadas e segregadas; não emitir pedidos ou alterar estoque por uma "conexão do grupo".

**Estoque comercial:** como as duas contas Bling são independentes, NÃO pressupor sincronização comercial automática entre suas quantidades, mesmo que cada marketplace utilize integração Bling. Se houver configuração adicional de Bling Multiempresas ou estoque virtual compartilhado, verificar comportamento e mapear suas regras como INTEGRAÇÃO EXTERNA explícita; não criar estoque físico pelo espelhamento, não sobrescrever balanços cruzados e não confundir saldo comercial com estoque gerencial do grupo. A disponibilidade publicada por cada conta é um dado de integração, não a fonte de propriedade patrimonial do MVet.

**Estado do código 2.0:** apps/integrations/bling.py ainda usa conexão `pk=1`, `settings.BLING_ISSUER_CNPJ` único e allowlist de endpoints GET, PATCH preço e POST balanço de estoque; **não existe** POST de pedido de venda na allowlist. apps/integrations/scheduling.py usa `BlingSchedule.kind` globalmente e `BlingConnection(pk=1)`; apps/integrations/bank_services.py também usa `pk=1`. Implementar adaptação explícita em todos esses pontos e nas views, workers, testes e comandos — não apenas remover constraint singleton.

### 5.2. Entidade IntercompanyOperation

Registrar: UUID-chave idempotente, seller_company, buyer_company, status, date, itens (SKU, qty, estoque local, seller_cost_snapshot, imposto/regra, preço, CMV comprador), pedidos Bling, IDs externos/conexão, NF saída/entrada, alocações origem da venda ao consumidor, lançamento da propriedade fiscal, título a pagar da compradora, liquidação/recebimento, divergências e histórico/auditoria. A direção pode ser Mercadovet -> MVet Agro OU o inverso; nunca hardcode Mercadovet fornecedora.

Ciclo: (1) vender ao consumidor pela empresa certa; (2) registrar pendência de origem; (3) gerar proposta de abastecimento com custo/tributo da fornecedora; (4) confirmar criação de pedido de venda no Bling da fornecedora, com proteção de replay e checagem remota após timeout; (5) associar documento fiscal emitido e entrada correspondente; (6) lançar transferência de propriedade sem alteração física, caso mesmo depósito; (7) gerar conta a pagar na compradora, não gerar contas a receber operacionais na fornecedora; (8) conciliar baixas e créditos bancários; (9) encerrar pendência. Admitir lotes, parcelas, múltiplas vendas, pagamento parcial, cancelamento e devolução.

Emissão/CFOP/legalidade são realizados fora do ERP no Bling; não criar emissão fiscal no MVet.

### 5.3. Não alterar histórico externo nem emitir duplicado

Criar intenção de escrita remota persistida (OUTBOX) com chave própria + empresa/conexão + hash do payload, estado PENDING/SENT/ACK/UNKNOWN/FAILED e referência externa. Não repetir POST remoto automaticamente se resposta foi ambígua; consultar situação no Bling, reconciliar manualmente se necessário. Salvar ID pedido/NF no banco e controlar unicidade por conexão. Nunca usar o token da outra empresa. Testes para HTTP429, token expirado, indisponibilidade, duplo clique e retorno incompleto.

## 6. Consolidação operacional, financeira e gerencial

Implementar seletor Mercadovet / MVet Agro / Grupo com indicação inequívoca do contexto. Contexto grupo é read-only.

**Estoque:** físico consolidado por SKU/local = soma assinada por CNPJ; propriedades visíveis lado a lado; não somar físico + saldos de propriedade como se fossem quantidades diferentes; mostrar pendências interempresa, estoque negativo por CNPJ, limites por local e Full.

**DRE:** individual por CNPJ: receitas externas/internas, CMV, impostos, fretes, taxas, comissões, variância de custo, despesas, EBITDA/resultado. Consolidado: somar resultados individuais com eliminação EXPLÍCITA das receitas/vendas internas e custos correspondentes, mais eliminação de lucro interno em mercadorias ainda em estoque quando houver. Tributos e gastos pagos a terceiros não desaparecem. Oferecer memória de cálculo e origem do lançamento; não somar indiscriminadamente duas DREs e chamá-las consolidadas. Tratamento do custo gerencial e eventual tributo não recuperável incorporado ao estoque merece regra identificada e testada.

**Financeiro:** contas bancárias da Mercadovet e da MVet Agro pertencem a CNPJs distintos; grupo soma posição bancária real de ambas, e transferências entre as empresas não geram receita econômica consolidada. Saldo realizado no cartão até hoje; projetado até o fim do filtro, conforme comportamento vigente. Previsões/pagamentos por empresa, sem dois títulos para uma única obrigação. Não criar recebíveis novos para vendas em geral ou interempresas; preservar legados já existentes.

**Comissões:** sempre partir da venda da empresa; preservar base PRODUCTS ou PROFIT, receita, imposto, CMV efetivo, parcelas, liberação por recebimento e estornos. Grupo pode agregar total de custo e passivos, nunca pagar duas vezes.

**CRM/alertas/arquivos:** consultas por empresa e modo grupo autorizado, exports respeitam o mesmo escopo e redigem dados sensíveis conforme permissões. Downloads e endpoints JSON devem ser protegidos pelo mesmo escopo.

## 7. Ambiente seguro e checkpoints

- MVet 2.0 produção: C:\Mercadovet\mvet, branch main, porta 8000, Compose/volume atual. Não tocar durante desenvolvimento.
- MVet 3.0 laboratório: C:\Mercadovet\mvet3, branch develop/mvet-3.0 ou PR de feature, porta 8001, projeto Compose NOMINAL separado (ex.: mvet3), PostgreSQL volume próprio, .env próprio, host e portas únicos.
- Validar que rede, bind mount, env_file, POSTGRES_HOST, db, migration e worker não apontam para produção. Faça comando de auditoria para mostrar nomes de container/projeto/volume (sem segredos).
- Não copiar credenciais Bling válidas para laboratório; bloquear comunicação de integração externa por configuração fail-closed e, idealmente, egress. O ambiente clonado deve estar seguro também quando um usuário clica num endpoint manual, não apenas com worker desligado.
- Usar cópia do backup restaurável validado, sem registrar/commitar dump. Dados sensíveis protegidos localmente. Melhor usar dados sintéticos para CI.
- Snapshot do código arquivo archive/mvet-2.0-2026-11-17 não substitui backup do banco; conservar referência do commit dc18da94... e registrar versão local do checkpoint.
- Antes da futura implantação, novo dump e ensaio de restauração da versão realmente instalada naquele instante, janela de manutenção, conciliação de saldos, plano de reversão que explicite perda/recuperação de lançamentos posteriores. Rollback do código sozinho pode ser incompatível com schema migrado.

## 8. Plano incremental de PRs, nesta ordem

**PR 0 — Infraestrutura 3.0, SEM alterar produção.** Documentar e testar Compose/projeto/volume/porta isolados, conexão Bling bloqueada, teste de restore e checks de identificação do banco; README de desenvolvimento. CI. Não criar empresa MVet nem lançar dados de teste em produção.

**PR 1 — Cadastro de empresas e autorização.** Converter Company singleton preservando pk1 Mercadovet, cadastrar MVet Agro inativa/sem operações até conclusão, UserCompanyAccess, seletor e modo Grupo somente leitura. Política explícita em backend, serviços e views. Testes de acesso cruzado e sessão.

**PR 2 — Identidade empresarial dos registros e migração do histórico.** FKs não nulas por empresa em vendas, compras, despesas, financeiro, comissões, CRM, notificações e conexões, por migrations aditivas/DDL compatíveis com triggers. Índices/constraints e verificação de FKs cruzadas. Zero perda/alteração de histórico ou IDs. Regressão integral em modo Mercadovet.

**PR 3 — Livro de estoque por proprietário/depósito.** Alterar saldos/movimentos e serviços transacionais com locks, valor/custo por empresa, físico grupo derivado e auditoria; preservar todas operações MVet 2.0, vendas negativas, custos locais e kits, contagem, transferência, fracionamento, planilha e planejamento. Aceite A/B/C (sem usar ainda POST Bling).

**PR 4 — Funções comerciais e financeiras completas em MVet Agro.** Reutilizar telas e fluxos para segunda empresa; vendas, compras próprias, impostos, parcelas, despesas, saldo bancário, comissões, CRM, notificações, PDFs/Excel, dashboard individual. Segurança e testes por empresa.

**PR 5 — UMA CONTA BLING INDEPENDENTE POR CNPJ.** Conexão OneToOne empresa, duas contas Bling independentes e autorizações OAuth distintas, tokens e refresh isolados, issuer verificado, filas de venda/compra separadas, IDs externos compostos por conexão, identificação de NF, comparação de estoque/preço por conexão, extrato bancário vinculado à empresa, workers/caches/agendamentos/status por CNPJ. Não presumir estoque comercial compartilhado entre as contas; caso haja sincronização Bling Multiempresas, homologar explicitamente. Sem token/operação cruzada; consulta real somente em homologação controlada e autorizada.

**PR 6 — Operações Interempresas bidirecionais.** Origem das unidades e déficit persistente; precificação, pedido Bling da fornecedora, NF vinculada, mudança de propriedade sem segundo físico, CMV provisório/definitivo sem duplicidade, contas a pagar e conciliação.

**PR 7 — Grupo consolidado.** Estoque físico único e posição por CNPJ, caixa, DRE e projeções, eliminações e memória de cálculo, relatórios/excel/PDF e permissões.

**PR 8 — Homologação em cópia recente e implantação separada.** Comparações estruturais e de saldos, carga, concorrência, interrupção, backup, ensaio de rollback, testes end-to-end dos dois Blings. Não fazer deploy sem aprovação explícita do usuário após todas validações.

PRs 2–4 podem ser subdivididos ainda mais para evitar mudança massiva e facilitar revisão; não saltar testes por pressa.

## 9. Testes mandatórios e critérios de aceite

### Regressão de TUDO que já existe

Executar o CI existente .github/workflows/tests.yml: Windows PowerShell updater, Django check, makemigrations --check --dry-run, migrate, setup_mvet, collectstatic, python manage.py test --verbosity 2 em PostgreSQL 16, testes de navegador/Chromium. Preservar ou ampliar os testes por módulo: inventory/tests.py e test_negative_sales/test_mvet15/test_transfer_batch/test_pricing_reconciliation, sales/tests.py e test_cost_corrections/test_context_corrections, purchases/tests.py, finance/tests.py e test_cash_cards/test_due_payments, integrations/tests.py/test_bank/test_stock_comparison/test_scheduling, commissions/tests.py/test_profit, expenses/tests.py/test_edit_bulk, reporting/tests.py/test_evolution/test_exports, CRM/tests.py/test_intake, accounts/tests.py e notifications/tests.py.

### Invariantes e casos obrigatórios

- Após migração, todas entidades históricas pertencem à Mercadovet (pk1); nenhum ID/revisão/CPF-CNPJ/quantidade/valor mudou; totais por SKU+depósito, saldo de cada banco, quantidade e valor de títulos, CMV efetivo, impostos, comissões e DRE coincidem com baseline.
- Usuário Mercadovet não lê/altera MVet Agro por URL, POST de FK, lookup SKU, API, exportação, PDF, popup, worker, cache ou relatório; inverso idem. Grupo somente para usuário explicitamente autorizado.
- SKUs iguais com custos médios distintos, preços mínimos e saldo por empresa; sem duplicação de produtos globais. Reposição por empresa não altera a média do outro CNPJ.
- MVet Agro vende 2 de Mercadovet 10: Mercadovet 10 / MVet -2 / físico8; ao fornecer 2: 8 / 0 / físico8; SEM duas saídas físicas. Cenário reverso também.
- Venda por empresa utilizando estoque próprio e da outra em proporções; dívida de origem persiste depois de compra externa, liquidável parcialmente.
- Compra externa MVet Agro +5 incrementa físico +5 e somente saldo/custo MVet Agro; compra externa Mercadovet idem.
- Mesma localização para dois proprietários, transferência entre locais, Full, kit de componentes, fracionamento, contagem, estoque negativo, bonificação, frete de compra fora NF, transferências múltiplas, reversões/cancelamentos e CMV histórico.
- Margens/CVM definitivo e StockMovement.cost_variance não duplicam mesmo custo na DRE; tributos interempresa conservados conforme efetivo; DRE individual e grupo reconciliam.
- Cada CNPJ importa apenas NF de sua conta Bling independente (mesmo número/série pode existir nas duas), idempotência ao reconsultar, preservação do vínculo mesmo após cancelamento e IDs externos por conexão; desconectar/reautorizar uma conta não afeta a outra. Testar OAuth state por CNPJ, expiração/refresh simultâneos, agendamentos independentes, consulta por conta e token cruzado bloqueado.
- Pedido interempresa em ambos sentidos não duplica em duplo clique/timeout/HTTP500; nenhum ajuste externo automático sem confirmação.
- Banco Bling de MVet Agro nunca confere com FinancialAccount da Mercadovet; saldos por empresa e grupo somam corretamente.
- Títulos, comissões, CRM e alertas segregados; módulos CRM, despesas, caixa e exportações permanecem usáveis na empresa secundária; nenhuma página só funciona com pk1.
- Restrições PostgreSQL preservam livro imutável e permitem apenas correção histórica auditada; backfill sem desativação insegura das proteções.
- Stress/concurrency de confirmação de venda, recebimento, transferência interempresa e agendamento; locks sem deadlock.
- Congelar baseline quantificado antes de migrações e produzir relatório de diferenças zero (ou mudanças aprovadas discriminadas) após cada fase.

### Critério de entrega por PR

1. Listar arquivos e modelos modificados, efeitos cruzados, riscos e plano de teste antes de alterar.
2. Migrations aditivas e cuidadosas, sem rebuild destrutivo ou IDs novos para histórico.
3. Testes backend, permissions, Django/PostgreSQL triggers, front e browser quando aplicável.
4. Validar relatórios e valores Decimal; indicar exatamente o que não pôde ser testado.
5. Atualizar ADR/documentos/CHANGELOG e descrever como reproduzir/voltar.
6. Abrir PR com base develop/mvet-3.0; só integrar após checks green.
7. Não mesclar main, nem mexer no Docker produção sem pedido expresso de implantação.

## 10. Primeiro comando/instrução do próximo chat

**Prompt curto de continuidade a ser usado com este documento:**

“Implemente o MVet 3.0 multiempresa no repositório andreiruck-max/mvet conforme docs/MVET_3_0_HANDOFF_MULTIEMPRESA.md na branch develop/mvet-3.0. Comece apenas pelo PR 0 (infraestrutura de desenvolvimento isolada, sem tocar em main, .env, banco de produção ou Bling real). Antes de escrever, leia AGENTS.md e os arquivos citados e audite o estado atual da branch. Preserve 100% das funcionalidades do MVet 2.0 para a Mercadovet e replique-as na MVet Agro, com visão de Grupo; estoque por proprietário/depósito e físico consolidado são a prioridade. Execute os testes pertinentes e entregue PR, evidências e próximos passos, sem deploy em produção.”

## 11. Pontos que não devem ser inferidos silenciosamente

- O projeto não substitui o Bling como emissor fiscal; não implementar emissão fiscal no MVet.
- Duas contas Bling independentes NÃO significam estoque comercial automaticamente unificado. Se houver Bling Multiempresas/depósito virtual externo, exigir teste específico; uma unidade espelhada NÃO é unidade física adicional.
- O custo da Mercadovet NÃO é automaticamente o custo da MVet Agro.
- A média do Produto global NÃO pode determinar CMV de uma das empresas.
- A perda fiscal/tributária efetiva e o lucro interempresa em estoque não devem desaparecer/duplicar na DRE do grupo por uma soma ingênua.
- O modo consolidado NÃO autoriza editar ambas empresas com uma só transação implícita.
- O snapshot de 17/11/2026 NÃO contém lançamentos posteriores; 3.0 não pode ser posto em produção usando snapshot antigo sem plano de atualização dos dados.
- O fato de a suíte de testes atual passar NÃO prova isolamento multiempresa; criar matriz nova de regressão e privacidade, de preferência testes parametrizados nos dois CNPJs.
