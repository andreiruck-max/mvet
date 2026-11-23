# ADR 0078 — Identidade empresarial do estoque legado

Etapa aditiva da fase 3 do MVet 3.0. StockBalance, StockOperation,
StockMovement, OpeningImport e InventoryReconciliation recebem company com
PROTECT e default constante 1. O DDL não atualiza linhas protegidas nem
suspende triggers. Empresa principal é garantida pela migration core 0015.

Restrições temporárias aceitam somente empresa 1. A unicidade produto/local,
os cálculos, locks e projeção Product permanecem legados nesta etapa: não
habilitar Agro nem interpretar esta entrega como estoque multiempresa pronto.
StockLocation e SKU continuam globais. A próxima etapa deve contextualizar
serviços, permissões, consultas, importações e contagens antes de remover
as restrições e alterar a unicidade para empresa/produto/local.

Teste de migration conserva todos os campos anteriores de saldos, operações,
movimentos e importações, incluindo transferência estornada, saldo negativo,
reposição com variância e totais Product. Verifica check_inventory, triggers
e bloqueio de proprietário secundário. CI executa regressão PostgreSQL e
navegador; dados exclusivamente sintéticos. Não é ensaio em backup operacional.

Reversão operacional exige backup compatível e ensaio próprio; não executar
rollback de schema em produção. Nenhuma alteração de main ou Bling real.
