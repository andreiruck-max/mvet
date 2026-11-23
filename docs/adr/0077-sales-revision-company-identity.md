# ADR 0077 — Empresa do histórico de correções e recuperação

Status: aceito na transição MVet 3.0.

SaleCorrection, SaleCostRevision e SaleRecovery recebem company obrigatório,
PROTECT, default Mercadovet e bloqueio secundário. Migration aditiva preserva
snapshots, valores, autor, motivo, revisões e operações de estoque vinculadas.
Os gatilhos imutáveis permanecem; nenhum CMV histórico é recalculado.

Teste PostgreSQL cria correção comercial, correção de custo e recuperação de uma
venda cancelada pelos serviços reais; compara todos os campos anteriores à migration
e a venda completa, e verifica a imutabilidade dos três históricos.

Contextualização dos serviços e FKs cruzadas ainda será necessária antes de remover
os bloqueios transitórios. Não habilita operação secundária.
