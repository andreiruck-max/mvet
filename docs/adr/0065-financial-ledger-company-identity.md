# ADR 0065 — Propriedade empresarial do livro financeiro

Continuação da PR 2: FinancialTitle, FinancialOperation, FinancialEntry, FinancialTitleRevision e DuePayment recebem FK company obrigatória, PROTECT, default constante 1 e constraint temporária limitando a Mercadovet. Com contas já restritas à empresa 1, nenhuma relação financeira pode atravessar empresas nesta fase.

DDL aditivo preserva registros imutáveis sem UPDATE de histórico, alteração de valores ou desativação de triggers. O default é transitório e será removido quando os serviços exigirem contexto explícito. Não habilita operações MVet Agro, não muda formulários, não executa baixas e não chama Bling.

Validação exige regressão financeira completa e PostgreSQL, incluindo pagamentos, estornos, revisões e agendamentos. Próxima etapa: identidade das origens comerciais e despesas, seguida de filtros e serviços por empresa; só então remover os bloqueios transitórios.
