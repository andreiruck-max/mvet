# ADR 0081 — Proprietário do estoque deriva do documento

Confirmação/cancelamento de venda, recebimento/cancelamento de compra,
recuperação e correção de venda validam contexto empresarial antes do replay
ou de alterações. Operação de estoque recebe explicitamente a empresa da
venda/compra; cálculo de custo e cronologia usam essa empresa. Consumos e
revisões criados nesses fluxos persistem a mesma identidade.

Ao reverter ou relocar uma operação existente, conferir que operação e suas
pernas pertencem à empresa do documento. Mismatch bloqueia atomicamente,
sem reatribuir movimentos, refazer CMV histórico ou recriar financeiro.

Não libera Agro: configuração, rascunhos, FKs e consultas comerciais ainda
precisam de adaptação completa. Restrições primárias permanecem ativas.
Testes novos cobrem grupo sem confirmação/replay/recebimento/cancelamento,
origem incompatível e recebimento/estorno na empresa da compra. Regressões
existentes cobrem kits, variância, correção, recuperação e CMV congelado.
