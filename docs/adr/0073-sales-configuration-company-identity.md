# ADR 0073 — Empresa dos canais e histórico tributário

Status: aceito na transição MVet 3.0.

SalesChannel, TaxRule, TaxRateChange e SaleTaxRevision recebem company obrigatório,
PROTECT, default Mercadovet e constraint transitória company=1. A migration é aditiva:
não reescreve alíquotas, vigências, snapshots, revisões nem vínculos de comissão.

Os serviços ainda não aceitam operação secundária. Unicidades existentes e gatilhos
imutáveis permanecem. A separação das consultas/configurações e a validação de FKs
entre empresas precederão a remoção dos bloqueios. Não é ativação multiempresa.

Teste PostgreSQL cria venda confirmada e recálculo tributário auditado, migra de/para
o schema anterior e compara todos os campos históricos e a venda integralmente.
Verifica bloqueio secundário nos cadastros e imutabilidade das revisões tributárias.
