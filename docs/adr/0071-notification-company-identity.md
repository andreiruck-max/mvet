# ADR 0071 — Identidade empresarial das notificações

Status: aceito para a transição do MVet 3.0.

Notification, NotificationRead e NotificationPreference recebem company obrigatório,
PROTECT e default transitório Mercadovet. A migration adiciona colunas sem reescrever
os valores históricos: revisões, leituras, preferências e IDs são preservados.
Constraints bloqueiam empresas secundárias enquanto geração, consultas e permissões
não receberem contexto empresarial explícito. As unicidades existentes permanecem.

BackupEvidence continua evidência da instalação inteira. AlertConfiguration ainda
é global; a separação dos alertas operacionais e do monitoramento do backup deve
preceder a ativação multiempresa. Alertas BACKUP históricos continuam associados à
Mercadovet nesta transição, sem multiplicar evidências por CNPJ.

Teste PostgreSQL migra registros antigos e compara todos os campos anteriores,
inclusive revisões e datas, e verifica rejeição de empresa secundária nos três modelos.
A suíte existente cobre refresh idempotente, permissões, concorrência e navegador.
Esta etapa não habilita uso operacional da Agro nem isolamento completo dos workers.
