# ADR 0059 — Parceiro comercial com comissão sobre lucro

Data: 13/11/2026. Status: aceito para implementação na PR 90, sem merge autorizado.

## Decisão

Adicionar PARTNER_PROFIT sem reinterpretar silenciosamente PARTNER histórico. CommissionPlan.basis fixa PRODUCTS ou PROFIT por plano; migração mantém PRODUCTS nos planos antigos. Alterar explicitamente o tipo da pessoa converte seus planos, com auditoria e compensações. Alterar percentuais padrão continua afetando apenas novas definições.

PROFIT = receita líquida operacional (incluindo frete recebido e ajuste de receita) − frete pago − taxas − deduções (DIFAL, outros custos e custos adicionais) − imposto − CMV efetivo. A própria comissão é excluída da base para evitar circularidade. A base percentual mínima é zero. O total manual permanece prioritário. Distribuir o total por igual entre parcelas, conservando centavos com arredondamento acumulado. Recebimento parcial libera proporcionalmente dentro da parcela.

Alteração de alíquota efetiva, inclusive a partir de hoje, recalcula planos PROFIT das vendas confirmadas abrangidas pela revisão tributária; imposto manual permanece preservado. Correções de valores e de CMV também sincronizam o plano. A nova comissão substitui o custo da venda via SaleCorrection, sem duplicar DRE ou gerar financeiro.

Rebalanceamento insere somente diferenças de liberação, com motivo, período e revisão tributária. Entry.terms registra a base utilizada. Pagamentos e alocações não são alterados. Diferenças negativas compensam próximos pagamentos; positivas ficam pendentes. Cancelamento/devolução integral local usa o estorno de liberação existente. Recuperação atualiza base e restaura liberações. A sincronização do Bling não passa a cancelar vendas automaticamente; devolução parcial não ganha um fluxo novo neste lote.

## Validação

Cobrir fórmula antes da comissão, divisão igual e centavos, recebimentos parciais, recálculo positivo/negativo após pagamento, período tributário, total manual, prejuízo, cancelamento/recuperação, conversão explícita e correção do CMV. Validar triggers e transações no PostgreSQL pelo CI. Nenhuma alteração em main nesta etapa.
