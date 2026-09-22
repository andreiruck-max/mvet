# ADR 0019 — MVet 1.5: custo médio por depósito

Decisão solicitada em 22/09/2026: cada venda deve consumir quantidade e custo do depósito escolhido. Substitui a política de custo global para novas saídas, preservando o CMV de vendas antigas.

StockBalance mantém quantidade (4 casas), valor e média (6 casas). Product continua sendo a soma consolidada, com média informativa ponderada. Entrada e compra ponderam somente o depósito recebedor. Saída e venda absorvem o resíduo na última unidade do depósito. Transferência leva o custo de origem e pondera o destino, conservando quantidade e valor globais. Fracionamento e kit usam o depósito de origem. Correção de custo afeta somente o local selecionado. Cancelamento de venda devolve o valor original; não usa o custo atual. Estorno preserva referência de custo zero local, com snapshot para novos movimentos e recuperação pelo livro para os legados.

Migração 0006 acrescenta projeções locais e recupera soma de movimentos por produto/local. Não atualiza movimentos, vendas, snapshots, caixa ou DRE. Confere somas com Product; saldo negativo, residual sem quantidade ou quantidade divergente bloqueia atomicamente a migração. Dados legados inconsistentes exigem conciliação específica, sem rateio silencioso. Posições iniciais por local preservam os valores originais importados. Downgrade após operações 1.5 exige restauração compatível: não voltar simplesmente o código.

Atualização em janela sem escritas, backup restaurável, migração e check_inventory antes de reabrir a operação. Locks existentes do domínio e ordem produto/local preservados.

Tela abre no depósito padrão configurado, com alternativa Mercadovet. Todos os depósitos permanecem consultáveis, inclusive inativos. Produtos sem saldo cadastrado no local aparecem zerados. Totais incluem ativos/inativos e todos os depósitos, não recebem filtros da lista. Usuários sem view_costs não recebem totais nem custos. Busca numérica é SKU exato; texto prioriza SKU exato e depois nome parcial ou prefixo alfanumérico. Ordenação numérica aceita até 60 dígitos sem conversão para inteiro de tamanho limitado. Exportações seguem o depósito selecionado.

Canal comercial e depósito são campos distintos: Mercado Livre pode operar tanto Loja como Full. A confirmação usa obrigatoriamente o depósito gravado na venda, inclusive na revisão de notas Bling. Não inferir Full apenas pelo nome do canal. Na revisão, o operador precisa selecionar o depósito correto.
