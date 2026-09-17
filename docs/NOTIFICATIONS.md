# Notificações internas

Central em `/notificacoes/`, com lista paginada (30), filtros por situação, leitura, tipo e severidade, link ao registro e leitura individual. Preferências pessoais não alteram as dos demais usuários. Configuração global exige `core.manage_configuration`; alterações e preferências são auditadas.

## Condições implementadas
- Estoque: produto simples ativo, mínimo maior que zero e quantidade global menor ou igual ao mínimo. Quantidade soma os locais; transferência Mercadovet/Full não altera esse total. Mínimo zero desabilita o alerta do produto. Kits virtuais não têm estoque próprio e ficam fora desta regra.
- Margem: venda confirmada abaixo do limite salvo na venda ou contribuição negativa. Negativa é crítica, baixa é atenção. Inclui imposto retroativo e taxas extras pelos valores efetivos da venda; nunca recalcula CMV. Cancelamento resolve no próximo processamento.
- Vencimentos: títulos abertos a pagar e receber com principal restante, até a antecedência configurada (padrão 3 dias). Futuro é informação, hoje atenção, vencido crítico. Liquidação integral/cancelamento resolve; parcial atualiza saldo. Inclui parcelas de compras, despesas e recebíveis.
- Backup: habilitado explicitamente pelo administrador. Falha registrada é crítica; ausência de sucesso após o prazo configurado também. Antes da primeira execução, conta-se desde a ativação. Sem evidência, o sistema não afirma sucesso. Prazo padrão 36 horas.

## Leitura e segurança
Estoque exige `operate_stock`, `operate_sales` ou `view_costs`. Margem exige `view_costs`, também exigida para detalhes individuais da venda. Financeiro exige `operate_finance` ou `view_finance`; backup exige `manage_configuration`. `view_dashboard` sozinho não concede custos individuais. Escopo reavaliado em cada requisição HTML/API e ao marcar lida. Contagens, filtros e links obedecem ao mesmo escopo. Preferência pessoal ou configuração global desabilitada oculta a categoria, inclusive histórico.

Um registro por tipo/entidade evita duplicação; cada usuário tem sua leitura. Mudança de conteúdo/severidade ou reativação incrementa revisão e exige nova leitura. Reprocessamento idêntico conserva leitura/data. Resolução conserva histórico. Marcar revisão antiga recebe 404 para não consumir atualização invisível ao usuário. Não há envio externo.

## Processamento
```sh
docker compose exec -T web python manage.py refresh_notifications
```
Agendar a cada 15 minutos no servidor (cron ou Agendador do Windows/WSL), com diretório do projeto e log de saída/erro. Administrador também pode usar **Atualizar alertas**. Central informa horário do último processamento; não é tempo real. Agendamento na máquina da empresa não é instalado automaticamente pelo código.

Comando roda em transação própria e usa lock PostgreSQL exclusivo das notificações para serializar reprocessamentos, preferências e leitura. Não usa lock de estoque/financeiro nem é chamado dentro de confirmação de venda ou pagamento. Falha reverte somente processamento e preserva avisos anteriores; não impede operações normais. Condições que mudarem durante a leitura serão refletidas na execução seguinte. Consulta iterada no servidor; navegador não carrega todo histórico.

## Backup
`scripts/backup.sh` registra sucesso após dump não vazio e catálogo validado por `pg_restore --list`, com bytes e SHA-256. Falha tenta registrar evidência e preserva código de saída. Se banco/app estiver indisponível, não há como gravar evidência naquele momento: log do agendador é necessário; ao voltar, ausência de sucesso recente gera alerta. `record_backup` é comando administrativo, não endpoint público, e confia no script/operador do servidor. Não aceita sucesso sem tamanho positivo e hash válido. Não demonstra cópia externa ou restauração: consultar `BACKUP_RESTORE.md`.

Importações externas e detector de inconsistências integrados à central ficam para integrações; `check_inventory` permanece separado. Não há dados fictícios nem avisos de integrações inexistentes.
