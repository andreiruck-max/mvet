# Controle de comissões

## Operação
1. Em Comissões → Comissionados e percentuais, cadastre a pessoa. Usuário é opcional: representantes/parceiros não precisam de login. Percentual manual da venda tem prioridade sobre o da pessoa e o global; zero é um percentual válido. Alterar padrões não recalcula vendas anteriores.
2. Abra uma venda confirmada → Controle de comissão, ou Definir comissão de venda. Informe pessoa, cliente e cronograma. Parcelas iguais podem ser geradas por quantidade, primeiro vencimento e intervalo; para valores diferentes informe uma linha DD/MM/AAAA;valor. As parcelas devem reconciliar produtos − desconto + frete recebido. Ajuste gerencial de receita não integra essa base contratual.
3. Base elegível = produtos − descontos. Frete nunca integra comissão. Rateio proporcional aos valores das parcelas, com arredondamento acumulado que conserva centavos. A comissão prevista substitui o campo comissão da venda, com SaleCorrection; não cria segunda despesa na DRE. Somente vendas selecionadas para controle recebem comissionado; vendas sem comissionamento continuam válidas.
4. Registrar recebimento em cada parcela libera valor proporcional. Pode antecipar parcela futura informando recebimento efetivo hoje. Pagamento ainda não realizado não deve ser registrado. Data de novo evento não pode preceder o último evento da parcela.
5. Apuração mensal usa data da liberação e ajustes na data efetiva. Exibe pagamento por data e, separadamente, valores alocados às liberações do mês. Saldo anterior inclui liberações anteriores menos pagamentos alocados até o encerramento. Histórico de competências usa termos gravados em cada evento.
6. Registrar pagamento permite parcial e aloca automaticamente às liberações mais antigas, até o mês escolhido e nunca posteriores ao pagamento. A posição atual e a posição da data limitam o pagamento; compensações negativas reduzem o disponível. Pagamentos/estornos preservam alocações por evento, venda e parcela.

## Relação com financeiro
ADR 0022 permanece: novas vendas não geram recebíveis. Recebimentos neste módulo são comprovação manual para apuração, sem criar título ou crédito bancário; não são sincronizados com recebíveis históricos. Pagamento de comissão é registro da quitação realizada fora do módulo: não cria débito bancário nem outra despesa. Caso controle caixa no MVet, o débito deve ser lançado/conciliado uma única vez no financeiro, sem cadastrar despesa por competência adicional à comissão já incluída na venda. Integração bancária automática é evolução futura, não comportamento implícito.

## Correções e estornos
- Ajustar comissão altera percentual/total manual, com motivo, ator, antes/depois e revisão. Diferença já liberada é lançada hoje, preservando eventos antigos; custo da venda/DRE é corrigido pelo mecanismo auditado existente.
- Correção de produtos/desconto na venda recalcula base e comissão; cronograma/recebimentos mantêm valores contratados e pesos originais. Divergência com valor atual aparece na ficha. Revisar parcelas permite conciliar valores/vencimentos, preservando cada parcela e impedindo reduzir seu valor abaixo do recebido. Diferenças de liberação são registradas hoje. Uma correção de comissão controlada deve usar o módulo, e não editar comissão isoladamente na venda.
- Cancelar venda zera liberação por contrapartidas; recebimentos e pagamentos permanecem. Recuperar venda restaura liberação correspondente aos recebimentos líquidos. Comissão paga passa a saldo negativo até recuperação ou compensação.
- Estornar recebimento reduz recebido e liberação proporcional pelo percentual vigente. Estorno de pagamento registra valor e alocações negativos e reabre saldo. Não há exclusão ou alteração direta do livro.
- Saldo negativo de uma venda compensa saldo positivo de outras vendas da mesma pessoa; não transfere dívida entre pessoas. Detalhamento pode mostrar positivos e negativos que se anulam no resumo.

## Acessos e integridade
`core.view_own_commissions`: somente pessoa vinculada ao próprio usuário, inclusive fichas, apuração e pagamentos; sem escrita.
`core.manage_commissions`: gestão integral de comissões, inclusive pagamentos e correções; não concede bancos, CMV ou DRE. Master já possui acesso. Backend valida todas as ações; nenhuma permissão depende de nome de grupo.
Comissionado com histórico não pode trocar usuário já vinculado. Pode inativar sem excluir histórico; inativação impede novos planos, mas preserva recebimentos/pagamentos pendentes. Valores usam Decimal. Mutex de domínio e transações evitam pagamentos concorrentes; UUID/fingerprint impede reenvio divergente. Triggers PostgreSQL tornam comandos, liberações, pagamentos e alocações imutáveis. Sem editor transacional no admin.

## Validação
Cenários automatizados: frete/desconto; rateio desigual e centavos; recebimento parcial; idempotência; limite de pagamento; compensação; cancelamento/recuperação; ajustes; snapshot; mudança de base; corte mensal; escopo de usuário; concorrência PostgreSQL e proteção do livro. Browser: criar plano, receber parcela, pagar parcialmente, apurar e consultar como funcionário no celular.
