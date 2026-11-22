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

Cálculo e validação rejeitam regra de outra empresa, inclusive com imposto manual.
Sugestão e seleção para recálculo filtram pela empresa, sem fallback para outra regra.
Alterações e revisões recebem explicitamente a empresa de origem. O serviço de
alteração valida o contexto/autorização e rejeita Grupo. O default company_id=1
é somente compatibilidade transitória; a operação secundária permanece bloqueada.
