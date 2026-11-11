# ADR 0056 — Consulta periódica de notas em segundo plano

Data: 10/11/2026. Solicitação do proprietário: buscar notas automaticamente com periodicidade horária sem bloquear o uso, preservando busca manual.

Processo Docker independente `bling-worker`, sem filas externas/Celery. Configuração persistida por tipo, exclusiva master: ativação opt-in, intervalo de 1–168 horas e janela móvel de emissão de 1–366 dias (padrão 1 hora/7 dias). O responsável pela ativação é revalidado em cada página. Conexão desconectada gera erro recuperável; usuário inativo/sem permissão pausa o agendamento. A tela permite acompanhar execução, cursor, contagens e heartbeat. Sem worker recente (>10 minutos), não afirma que a busca esteja funcionando.

Uma página por passo, alternando tipos conforme prazo; datas congeladas no início do ciclo, vendas em situações 5/6, compras em 5/7. Canceladas ficam na busca manual. API, OAuth, limitação de requisições e serviços de staging existentes são reutilizados. Cada página tem até 300s no worker (HTTP manual mantém 40s). Falhas persistem mensagem e repetem a página após 5min; notas já recebidas não se perdem. Erros documentais ficam para conferência. O mesmo período pode ser reconsultado sem duplicar as identidades. Notas antigas fora da janela exigem consulta manual ou janela maior.

Lock advisory PostgreSQL de sessão impede dois workers automáticos simultâneos, sem transação longa ou lock de estoque durante rede. Morte do processo solta o lock; cursor durável permite retomada. Desativar/alterar incrementa revisão, impede término antigo de sobrescrever a escolha e vale após a página corrente. Atualizador interrompe worker antes de backup/migrações, preserva dados e o reinicia depois do web. SIGTERM encerra entre páginas. Erro inesperado tem log genérico sem tokens/payloads.

Manual continua disponível, com o bloqueio curto da conexão já existente; consultas concorrentes podem pedir nova tentativa e o automático retenta depois. Não transforma confirmação em tarefa automática, não aprova notas, não cria rascunhos de compra, não gera estoque, vendas confirmadas, parcelas ou caixa. Homologação com credenciais reais depende da ativação na instalação.
