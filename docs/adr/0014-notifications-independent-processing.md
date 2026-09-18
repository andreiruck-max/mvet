# ADR 0014 — Processamento independente de notificações

Status: aceito. Data: 17/09/2026.

Alertas devem acompanhar estoque, resultados e vencimentos sem causar falhas em vendas/pagamentos ou expor finanças aos operacionais.

Decisão: processamento periódico explícito em transação/lock próprios, condição única por tipo/entidade, revisões para leitura por usuário e permissões reavaliadas no acesso. Preferências pessoais e habilitação global são independentes. Links construídos com rotas conhecidas, sem URL arbitrária. Condições resolvidas permanecem consultáveis.

Backup usa evidência produzida pelo script validado; habilitação e prazo explícitos impedem assumir que existe agendamento. Falha de banco pode impedir registro; logs do agendador e alerta por ausência de sucesso são complementares.

Consequências: consistência eventual, com horário do último processamento visível. Administrador instala agendamento na empresa. Mudanças de conteúdo reiniciam leitura; reexecução idêntica não. Central não comprova restauração/cópia externa e não envia mensagens fora do ERP.
