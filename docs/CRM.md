# CRM / Comercial — primeira versão

## Operação
O Master libera **CRM: acessar e operar a própria carteira comercial** na tela Usuários e acessos. O grupo COMERCIAL é criado pelo setup sem atribuir usuários automaticamente. Nenhum funcionário ganha bancos, margens ou outras permissões. Usuário com CRM, sem indicadores, inicia nas pendências; Master mantém Dashboard.

Menu CRM: Pendências, Contatos, Novo contato. Master também tem Visão comercial, Aprovações, Importar contatos e Regras de retorno.

Nome e telefone/WhatsApp ou e-mail são obrigatórios; cidade é recomendada. Funcionário é responsável pelos contatos que cadastra; somente Master reatribui. Telefone brasileiro recebe código 55 e perde a formatação; exterior usa +código do país. E-mail normalizado em minúsculas. Duplicidade por telefone/e-mail é bloqueada, inclusive entre carteiras e contatos inativos. Não revela a identidade de outras carteiras ao funcionário; Master confere e corrige o existente. Não há fusão nem exclusão na interface.

Pendências são ordenadas por data (Atrasados, Hoje, Próximos). Pausados não aparecem antes da data; voltam automaticamente quando alcançada. Estado Pausado é preservado até nova ação, mas a data passa a vencer normalmente: não depende de cron ou de manter uma aba aberta. A seção Próximos permite antecipar a preparação; os contatos futuros não contam como tarefas de hoje.

## Contato e recorrência
Histórico acumula data/hora, autor, canal, tipo de atividade, mensagem enviada, recebida, visualização manual, resultado, observação interna e próxima ação. Mensagens são textos distintos preservados literalmente; HTML é escapado. Informações comerciais importantes ficam na ficha. Alterações cadastrais são auditadas.

Regras iniciais: interessado/não respondeu/outros 7 dias; aguardando resposta, cotações solicitadas/enviadas 3; visualizou sem resposta 15; sem interesse no momento 30; frio 60. Master deve revisar. Prazos de 1 a 3.650 dias, por resultado, com autorização de data manual. Alterar regra não recalcula combinações já feitas. Data automática parte da data local do contato registrado; uma anotação retroativa pode ficar imediatamente pendente. Não aceitar registro anterior ao último contato nem contato no futuro. Data manual deve ser hoje ou posterior.

Botões +3/+7/+15/+30/+40/+60/+90 contam de hoje. Sem data manual aplica a regra. Bloqueio de edição de data também protege pausa/reagendamento após resultado com essa restrição. Registrar venda realizada é resultado comercial, não cria venda, estoque ou financeiro.

Pausa exige data e motivo. Inativação exige justificativa e aprovação master; até decidir, fica fora da rotina em Solicitação de inativação. Recusa exige nova data; aprovação preserva histórico em Inativo. Pedido explícito de não receber contato usa **Não contatar**, imediato, ou o resultado correspondente. Sem recorrência/atalho WhatsApp; prevalece sobre pedido de inativação em aberto. Reativação apenas master, com responsável, data e justificativa; se era Não contatar, documentar nova autorização.

## Importação
CSV UTF-8 com vírgula/ponto e vírgula; XLSX de valores na primeira aba, sem fórmulas. Máximo 5 MB, 20 MB descompactado, 2.000 linhas e 30 colunas XLSX. Cabeçalhos aceitos documentados na tela. Nome e contato obrigatórios, demais campos opcionais. Responsável = login exato; vazio usa responsável padrão obrigatório. Datas iniciais escolhidas pelo Master.

Prévia não cria contatos. Confirmação explícita importa somente linhas válidas, mostrando relatório das rejeitadas. Duplicidades dentro do arquivo/banco e novas duplicidades surgidas após prévia não criam outro contato. Não sobrescreve nem mescla cadastros. Repetir confirmação da mesma prévia não duplica. Se a data inicial ficou no passado, gere nova prévia. Arquivo binário não é guardado; linhas da prévia e resultado permanecem no banco para rastreio e devem receber o mesmo cuidado de backup/privacidade que o restante do CRM.

## Master e controles
Filtros por responsável, cidade, segmento, origem, status, último resultado e datas. Visão Master tem atividades hoje/no período, novas pessoas cadastradas, atrasos, hoje, aguardando resposta, solicitações, carteira e atividades por funcionário. Período mede atividades e cadastros; pendências/status são posição atual. Contatos ativos sem data são impedidos no banco e ainda possuem verificação diagnóstica. Contatos de responsáveis inativos são destacados para reatribuir.

Serviços atômicos, lock de domínio e revisão otimista evitam perda de agenda em abas simultâneas. Envio de interação tem UUID único. PostgreSQL impede edição/exclusão de interações e eventos. FKs protegidas preservam vínculos. Carteira é filtrada no backend em todas as rotas; endpoints master exigem superusuário ativo. Não há admin transacional, API pública, WhatsApp automático nem IA nesta versão.

## Limites deliberados
Sem integração fiscal, pedidos, funil de oportunidades, anexos ou disparos. Histórico comercial contém dados pessoais: restringir acessos e backups. Importações devem vir de base legitimamente mantida pela empresa. Não contatar deve ser respeitado também fora do MVet; o sistema não controla o WhatsApp do funcionário.
