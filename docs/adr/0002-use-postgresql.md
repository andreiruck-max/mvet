# PostgreSQL
Status: aceito. Data: 15/09/2026.

## Decisão
Locks e transações exigem PostgreSQL em produção e CI. SQLite não valida concorrência e não será backend de produção.

## Consequências
Preservar em serviços, testes e documentação. Mudança exige ADR e avaliação de compatibilidade histórica.
