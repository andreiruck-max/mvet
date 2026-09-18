# Modelo de dados
Modelo alvo; implementação real identificada no BACKLOG. Não existem tabelas mensais. Datas são atributos. FKs históricas usam PROTECT e transações possuem status/reversões. Group e Permission nativos representam Role e Permission.

```mermaid
erDiagram
    User }o--o{ Group : possui
    Group }o--o{ Permission : concede
    User ||--o{ AuditLog : realiza
    Brand ||--o{ Product : marca
    ProductCategory ||--o{ Product : classifica
    Product ||--o{ ProductComposition : compoe
    Product ||--o{ StockBalance : saldo
    StockLocation ||--o{ StockBalance : local
    Product ||--o{ StockMovement : movimenta
    StockLocation ||--o{ StockMovement : local
    StockMovement o|--o{ StockMovement : reverte
```

```mermaid
erDiagram
    SalesChannel ||--o{ Sale : canal
    TaxRule o|--o{ Sale : snapshot
    Sale ||--o{ SaleItem : contem
    Product ||--o{ SaleItem : produto
    Sale ||--o{ StockMovement : consome
    Supplier ||--o{ Purchase : fornece
    Purchase ||--o{ PurchaseItem : contem
    Product ||--o{ PurchaseItem : produto
    Purchase ||--o{ FinancialTitle : parcelas
    Sale ||--o{ FinancialTitle : recebiveis
```

```mermaid
erDiagram
    FinancialAccount ||--o{ FinancialTransaction : lancamentos
    FinancialTitle ||--o{ FinancialTransaction : liquidacoes
    FinancialTransfer ||--|{ FinancialTransaction : pernas
    Expense ||--o{ FinancialTitle : pagar
    ChartOfAccount o|--o{ ChartOfAccount : hierarquia
    ChartOfAccount ||--o{ Expense : competencia
    ChartOfAccount ||--o{ ClassificationRule : classifica
    ImportBatch ||--o{ ImportRow : valida
    User ||--o{ Notification : recebe
```

## Campos e restrições do modelo alvo
- Product: SKU único, status, tipo, marca, categoria, unidade, mínimo, quantidade/valorização global e custo médio.
- StockBalance: unique(produto, local), quantidade não negativa.
- StockMovement: quantidade/valor assinados, custo snapshot, ator, data efetiva, horário do registro, origem, referência e reversal_of.
- Sale: série/NF únicas quando preenchidas, canal/data indexados, estado, valores, regra/alíquota/base/imposto snapshot; SaleItem com quantidade, SKU/nome/custo/CMV snapshot.
- Purchase: fornecedor/documento/data/status/itens. FinancialTitle substitui duplicação de estruturas de parcelas de compra e recebíveis de vendas.
- FinancialTitle: origem, tipo pagar/receber, vencimento, valor, competência quando aplicável, estado e flag de abertura.
- FinancialTransaction: conta/data/tipo/valor/status/ator, origem, vínculo de liquidação e reversão. Transferência gera duas pernas do mesmo valor.
- ChartOfAccount: código único, pai opcional, natureza DRE/patrimonial, status.
- ImportBatch: origem/hash/arquivo/metadados/contadores; ImportRow: conteúdo validado, erros e registro criado. unique(source, external_id) nos destinos pertinentes.

NUMERIC: quantidades 4 casas, custo/valorização 6, dinheiro 2. Índices por vencimento/status, conta/data, canal/data, produto/local. IDs internos independem de SKU/NF.

## Entidades concretas da Fase 2
```mermaid
erDiagram
    Product ||--o{ StockBalance : saldos
    StockLocation ||--o{ StockBalance : locais
    Product ||--o{ StockMovement : livro
    StockOperation ||--|{ StockMovement : movimentos
    StockLocation ||--o{ StockMovement : local
    Product ||--o{ ProductComposition : kit
    Product ||--o{ ProductComposition : componente
    User ||--o{ StockOperation : autor
    User ||--o{ OpeningImport : carga
    Brand ||--o{ Product : marca
    ProductCategory ||--o{ Product : categoria
```
Product mantém quantity/value/average_cost como projeção; StockBalance quantidade por local. StockMovement guarda deltas de quantidade/valor, custo unitário e posição global antes/depois. StockOperation agrupa tipo, data, motivo, autor, chave idempotente, hash do pedido e ligação única de estorno. OpeningImport guarda hash do arquivo e relatório, sem anexar a planilha ao repositório. Brand/ProductCategory/StockLocation têm ativo/inativo.

## Implementação da Fase 3
As seguintes entidades agora existem em migrations, além do modelo futuro descrito acima.

```mermaid
erDiagram
    SalesChannel ||--o{ Sale : canal
    TaxRule o|--o{ Sale : regra
    StockLocation ||--o{ Sale : local
    Sale ||--|{ SaleItem : itens
    Product ||--o{ SaleItem : produto
    SaleItem ||--o{ SaleConsumption : consumos
    StockMovement ||--o| SaleConsumption : snapshot
    StockOperation o|--o| Sale : confirmacao
    StockOperation o|--o| Sale : cancelamento
```

Sale armazena data comercial, NF/série únicas, UUID de criação, revisão, valores, snapshot tributário/margem mínima, estado e atores/horários. SaleItem conserva SKU/nome, quantidade, custo unitário e CMV. SaleConsumption liga cada componente efetivamente baixado ao item; imutável. Operações de estoque usam data física atual. Cancelamento preserva snapshots e vincula retorno ao movimento original.

## Adaptações da Fase 3
Company.default_stock_location referencia StockLocation (opcional em instalação existente). Sale.extra_costs_total agrega SaleExtraCost; linhas congeladas após confirmação. TaxRateChange registra novas alíquotas/base por data; SaleTaxRevision conserva recálculos individuais imutáveis.

```mermaid
erDiagram
    Company }o--o| StockLocation : padrao
    Sale ||--o{ SaleExtraCost : taxas
    TaxRule ||--o{ TaxRateChange : vigencias
    TaxRateChange ||--o{ SaleTaxRevision : recalculos
    Sale ||--o{ SaleTaxRevision : historico
```

## Implementação da Fase 4

```mermaid
erDiagram
    Supplier ||--o{ Purchase : compras
    StockLocation ||--o{ Purchase : destino
    Purchase ||--|{ PurchaseItem : itens
    Product ||--o{ PurchaseItem : produto
    Purchase ||--o{ PurchaseInstallment : parcelas
    StockMovement o|--o| PurchaseItem : recebimento
    StockOperation o|--o| Purchase : entrada
    StockOperation o|--o| Purchase : cancelamento
```

Purchase armazena totais, revisão/UUID, documento/série únicos por fornecedor, estados e atores/datas. PurchaseItem conserva preço, subtotal, rateio monetário, custo unitário e SKU/nome. PurchaseInstallment contém obrigação planejada ou confirmada; na Fase 5, situação financeira deriva do título vinculado. Triggers protegem snapshots confirmados/recebidos e permitem vincular movimento no recebimento e cancelar parcelas.

## Fase 5 — entidades implementadas
```mermaid
erDiagram
    FinancialAccount ||--o{ FinancialEntry : registra
    FinancialOperation ||--o{ FinancialEntry : possui
    FinancialOperation o|--o| FinancialOperation : estorna
    FinancialTitle o|--o{ FinancialOperation : liquida
    FinancialAccount o|--o{ FinancialTitle : previsao
    PurchaseInstallment o|--o| FinancialTitle : obrigacao
    Sale o|--o| FinancialTitle : recebivel
```
FinancialTitle: direção, origem, principal, baixado, vencimento, conta prevista, categoria básica, abertura, status, revisão, UUID, ator/timestamps e fonte. FinancialOperation: UUID/fingerprint, tipo/status/data, principal/juros/desconto/efetivo e reversão única. FinancialEntry: conta/operação/valor com sinal; livro imutável. Saldo diário é derivado, não tabela editável.

## Fase 6 — entidades implementadas
```mermaid
erDiagram
    ChartOfAccount o|--o{ ChartOfAccount : superior
    ChartOfAccount ||--o{ ClassificationRule : destino
    ChartOfAccount o|--o{ Expense : classifica
    Supplier o|--o{ Expense : favorecido
    Expense ||--|| FinancialTitle : obrigacao
    Expense o|--o{ Expense : recorrencia
    Expense ||--o{ ExpenseRevision : correcoes
    User ||--o{ ExpenseRevision : autor
```
Expense conserva competência, documento, valor NUMERIC, fornecedor/favorecido, categoria/caminho/natureza e regra snapshots, centro de custo, status, UUID/fingerprint, título único, base/índice de recorrência, revisão e atores/datas. Restrição positiva e unique(base,índice). ExpenseRevision conserva motivo e antes/depois imutáveis. Plano tem código único, pai protegido, natureza e grupo/analítica. Relações concretas acima substituem a cardinalidade futura inicial de Expense/FinancialTitle.

## Fase 8 — notificações
```mermaid
erDiagram
    User ||--o{ NotificationRead : leitura
    Notification ||--o{ NotificationRead : revisao
    User ||--o{ NotificationPreference : prefere
```
Notification identifica condição única por tipo/entidade, conteúdo, severidade, revisão, resolução e timestamps. NotificationRead tem unique(notificação, usuário); revisão lida permite reabrir avisos atualizados. NotificationPreference tem unique(usuário, tipo). AlertConfiguration é singleton com habilitação global, antecedência, prazo de backup, início e última execução. BackupEvidence registra resultado, data, bytes e SHA-256; sucesso exige evidência não vazia. Relação polimórfica de Notification é resolvida pelo tipo e ID, com links fixos e autorização dinâmica, sem exclusão do histórico.
