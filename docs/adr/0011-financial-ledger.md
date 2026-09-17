# ADR 0011 — Obrigações, liquidações e livro financeiro
Status: aceito na Fase 5.

FinancialTitle representa obrigação, nunca dinheiro. Compras confirmadas geram um título por parcela; venda confirmada gera um recebível bruto, sem presumir a conta ou a data real de liberação de marketplace. O financeiro pode alterar vencimento/conta previstos e liquidar parcialmente. Não há geração automática de recebimentos a partir do simples faturamento.

FinancialOperation registra liquidação, transferência ou estorno. FinancialEntry guarda as pernas com sinal. Operações realizadas e pernas não admitem edição/exclusão. Transferência prevista pode apenas ser realizada com a data efetiva ou cancelada; alterações de valor/contas exigem cancelar e refazer.

Liquidação separa principal, juros/acréscimos e desconto/abatimento. Valor efetivo precisa ser exatamente principal + juros − desconto. Retenções de marketplace devem ser identificadas na observação; não alteram custos/margem da venda e não criam nova despesa na DRE automaticamente. A conciliação detalhada por tipo de retenção evoluirá com despesas/integrações.

O principal liquidado fica no título para filtros rápidos, protegido no PostgreSQL por reconciliação contra liquidações sem estorno. A data do estorno preserva o caixa histórico, enquanto o título volta a pendente na operação atual. Operações usam o mesmo mutex transacional dos módulos de origem, evitando corrida entre cancelamento e pagamento. Revisão otimista mais UUID/fingerprint normalizado bloqueiam duplo clique, inclusive pagamentos parciais.

Saldos são consultas ao livro; não existem linhas de saldo editáveis por dia. Abertura é o saldo no início do dia e fica bloqueada após uso. Títulos vencidos pendentes e transferências vencidas previstas são carregados para hoje na projeção. Títulos sem conta aparecem separados, nunca silenciosamente omitidos. Valores previstos não são garantia de disponibilidade.

Uma venda tem um título agregado nesta etapa, com vencimento da previsão restante e múltiplas liquidações; cronograma de parcelas de venda com vencimentos distintos é evolução posterior. Compras já possuem parcelas individuais. Plano de contas hierárquico e competência de despesas pertencem à Fase 6; o caixa não deve ser utilizado como substituto da DRE.
