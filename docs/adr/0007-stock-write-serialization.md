# ADR 0007 — Serialização de escrita do estoque
Status: aceito. Data: 16/09/2026.

## Decisão
Usar mutex transacional PostgreSQL para escrita de estoque/catálogo/composição, mais select_for_update em produtos em ordem crescente antes de saldos. Leituras permanecem concorrentes.

## Motivo
Kits, fracionamento, edição de composição, carga inicial e requisições idempotentes atravessam várias entidades. A serialização das seções curtas reduz as possibilidades de corrida e deadlock na implantação inicial.

## Consequências
Duas saídas simultâneas não podem consumir a mesma unidade; dois envios iguais não duplicam movimento. Há limite de throughput de escrita; para escalar, substituir somente após testes PostgreSQL equivalentes de concorrência e ordenação de locks. Não usar SQLite como prova dessas garantias.

Estorno somente da última operação ainda não estornada de cada produto. Datas de estoque não podem preceder movimentos existentes. Correções usam ajuste atual para preservar o custo histórico. Movimentos têm triggers de imutabilidade em PostgreSQL.
