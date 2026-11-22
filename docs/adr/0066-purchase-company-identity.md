# ADR 0066 — Identidade empresarial das compras

Purchase, PurchaseItem e PurchaseInstallment recebem company obrigatória com default constante 1 via DDL. PROTECT e constraints temporárias restringem documentos e seus filhos à Mercadovet, enquanto serviços e integrações ainda são legados. Não modifica custos, parcelas, quantidades, snapshots ou gatilhos de imutabilidade.

Fornecedor e catálogo SKU permanecem compartilhados nesta etapa. A ativação de outra empresa depende de contexto obrigatório nos serviços, validação dos relacionamentos e estoque por proprietário; o campo isoladamente não habilita multiempresa. Unicidades existentes permanecem até a adaptação das consultas e formulários.

Testes verificam recebimento, propriedade dos itens/parcelas/título e rejeição de empresa secundária. Exige ainda regressão PostgreSQL e navegador, e ensaio de preservação histórica antes da integração. Não executar em produção MVet 2.0.
