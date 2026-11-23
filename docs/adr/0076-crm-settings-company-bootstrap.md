# ADR 0076 — Fundação inicial e configurações empresariais do CRM

Status: aceito na transição MVet 3.0.

Migrations antigas criam configurações CRM antes do setup da empresa. A migration
core 0015 garante pk1 por get_or_create, sem atualizar qualquer campo existente,
e corrige a sequência. A reversão não exclui a empresa nem o histórico.

CRM 0006 depende dessa fundação e adiciona owning_company a RecurrenceRule e
IntakeSettings. Preserva regras, datas, limites, pausa e IDs. Bloqueio transitório
company=1 e singleton permanecem até contextualização das rotinas e formulários.

Fixtures de testes usam update_or_create para pk1, com valores explícitos somente
do próprio teste. Isso suporta tanto dados iniciais de migration quanto banco vazio
após flush. Não há update_or_create do cadastro operacional na migration.

Teste PostgreSQL parte de banco sem empresa principal e configurações existentes,
compara todos os campos após migration e verifica bloqueio secundário. Regressão
completa é obrigatória devido à criação inicial da empresa e fixtures compartilhadas.
