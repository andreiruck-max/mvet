# ADR 0035 — CRM recorrente, carteiras e histórico

Status: aceito. Data: 10/10/2026.

CRM operacional independente de estoque e financeiro. Contato simplificado com responsável obrigatório; funcionário opera somente sua carteira. Master é superusuário ativo e governa importação, regras, distribuição, inativação e reativação.

Uma próxima ação por contato, substituída atomicamente após interação, com snapshot no histórico. Ativo/aguardando/pausado exigem data no banco. Inativo/não contatar/em aprovação não possuem data. Retorno é consulta pela data local, dispensando agendador. Pausa vencida participa da fila mesmo mantendo o rótulo até nova ação.

Mensagens enviadas, recebidas e observação interna são campos separados, sem inferir visualização. Interações/eventos imutáveis no PostgreSQL; cadastro auditado. Nenhum resultado comercial cria venda ou financeiro. Regras novas não alteram compromissos anteriores. Data manual controlada por resultado; calendário e atalhos são auxiliares, servidor valida.

Não contatar é exceção à aprovação: pedido explícito bloqueia imediatamente novas recorrências e WhatsApp na interface. Master só reativa com justificativa documentando nova autorização. Inativação comum requer decisão; recusa devolve com data.

Telefone/e-mail normalizados e únicos, sem revelar outra carteira ao funcionário. Importação com prévia explícita, limites e rejeição de fórmulas. Revalidação no commit, linhas inválidas não importadas e confirmação idempotente. Sem merge automático de cadastros, sem integração WhatsApp/IA nesta fase.
