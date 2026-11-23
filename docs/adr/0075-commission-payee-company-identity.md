# ADR 0075 — Empresa dos comissionados e percentuais padrão

Status: aceito na transição MVet 3.0.

Payee e CommissionSettings recebem company obrigatório, PROTECT, default Mercadovet
 e bloqueio company=1. A migration preserva vínculos de usuário, percentuais e planos.
Criação de plano rejeita pessoa de outra empresa e consulta padrão pela empresa da
venda. O plano recebe explicitamente essa empresa.

Singleton de configuração e vínculo único de login permanecem até contextualização
completa das telas, consultas e pagamentos. Não habilita segunda empresa. Antes de
liberá-la, substituir unicidades globais por empresariais e exigir contexto em todos
os serviços. Nenhum plano anterior é recalculado por esta migration.

Teste PostgreSQL compara cadastros, padrão e plano existente antes/depois da migration,
e verifica bloqueio secundário. Regressões existentes cobrem recebimentos, pagamentos,
comissões sobre lucro e revisões de imposto.
