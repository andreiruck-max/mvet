# ADR 0058 — Baixas, compromissos e conferência (12/11/2026)

Decisão solicitada pelo usuário; substitui o corte em hoje de ADR 0037 na visão de caixa. Realizado inclui todas as operações POSTED até a data de cada coluna, inclusive datas futuras. Hoje continua usando datas até hoje. Realizado + previsto soma o mesmo livro às transferências PLANNED e ao principal ainda pendente dos títulos na data de vencimento (vencidos carregados para hoje), sem repetir baixas futuras. Conciliação Bling continua limitada à data do extrato, nunca a pagamentos posteriores ao período.

Compras a pagar abre em Hoje em diante / Todas não canceladas. Compromisso é o valor atual menos principal liquidado em datas anteriores a hoje, excluindo baixas estornadas. Baixas de hoje permanecem até amanhã; baixas futuras permanecem até o dia seguinte à baixa. Saldo pendente real continua amount-settled e governa novas baixas. Cartões, grupos e exportação usam o compromisso; não autorizam pagar novamente valores já liquidados. Grupos começam abertos e podem ser recolhidos.

Baixa parcial mantém serviço financeiro único e as regras de principal/juros/desconto. Atalhos explícitos e cálculo sugerido do valor efetivo no formulário, ainda editável. Não cria nova despesa ou nova competência.

Pagar no vencimento é autorização explícita para baixar no MVet, NÃO é instrução de pagamento bancário. DuePayment guarda conta, autor, ativação, resultado e operação. Worker separado processa até 50 por ciclo; apenas após vencimento, respeitando conta ativa, permissões atuais, mutex financeiro, saldo restante e cancelamento. Se desligado, processa ao voltar, com data do vencimento. Erros de domínio desativam a programação e ficam visíveis no título. Operação e encerramento da programação são atômicos; reexecução não duplica. Revisar permite desativar. Alteração do vencimento acompanha o título, alteração da conta prevista não muda a conta autorizada. Pagamento manual parcial reduz a futura baixa automática.

Conta prevista opcional na compra/manual e conferência Bling é persistida no rascunho e aplicada na criação dos títulos. Nenhuma baixa automática é habilitada por esse preenchimento.

Campos monetários exibem agrupamento pt-BR com precisão preservada. FormData normaliza para o formato original do campo; nomes, validação Django, digitação em centavos, campos opcionais/zero e custos de seis casas são conservados. Sem JavaScript, formulário original permanece funcional.

Conferência Bling de venda/compra usa a política explícita de modais existente, com totais/cliente/fornecedor e escolhas principais antes de tabelas auxiliares. Compras permanecem em rascunho até confirmação explícita no diálogo. Atualização/vínculo de produto permanecem no diálogo; confirmação concluída atualiza a lista original com filtros preservados.

Extrato Bling normaliza débito já negativo, datas ISO com horário e resíduos binários inferiores a 1e-9 de números float. Conta, período, situação, finitude e centavos continuam validados. Valores em texto com precisão excedente não são arredondados. Mensagem de erro identifica campo/página/situação, sem expor payload. Sem amostra real da conta afetada, a causa específica não pode ser atribuída com certeza; homologação real permanece necessária.
