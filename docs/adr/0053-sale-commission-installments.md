# ADR 0053 — Parcelas da venda destinadas ao controle de comissão

Data: 06/11/2026. Status: proposto, aguardando integração autorizada.

## Decisão
A venda mantém um cronograma opcional, com até 60 parcelas, em `commission_installments`. O rascunho aceita datas e valores explícitos na seção Definir parcelas para comissão. A soma deve corresponder a produtos menos desconto mais frete recebido; valores são positivos em centavos e datas não precedem a venda. Ausência de cronograma conserva uma parcela na data da venda. O cronograma participa da auditoria e da chave de idempotência, e é preservado ao editar rascunho. Vendas confirmadas preservam o cronograma original; correções posteriores continuam no módulo de comissões, com revisão e proteção dos valores recebidos.

A normalização de NF de saída do Bling preserva as parcelas informadas (`parcelas.data` e `parcelas.valor`); aprovação transfere o cronograma para a venda e o plano de comissão. Sem parcelas externas, mantém o comportamento padrão. A conferência exibe o cronograma e bloqueia sua inconsistência com o valor da venda. Não altera parcelas de compras. Importações já aprovadas não são reescritas.

Confirmar uma venda com pessoa explícita ou vinculada ao canal cria um plano usando essas parcelas, mantendo rateio proporcional e conservação dos centavos. Sem comissionado, grava os termos sem gerar plano. A ficha de definição posterior pré-preenche os termos da venda. Nenhuma dessas ações cria título a receber, movimento bancário ou liberação de comissão; recebimento continua explícito.

A descrição da transferência já era opcional; a interface passa a deixar isso explícito. Em branco, usa Transferência entre contas. Revisar parcelas de comissão dispensa motivo: em branco, grava Cronograma de comissão atualizado. Mantém ator, antes/depois, revisão, idempotência e permissões. Outras ações continuam exigindo motivo.

## Verificação
Serviços: cronograma desigual, conservação de centavos, datas do Bling, ausência de recebíveis, valores inválidos, idempotência e auditoria sem observação. Navegador: criar e editar venda com parcelas, excluir linha, confirmar, verificar mobile e revisão de vencimento sem motivo. Migração aditiva, sem atualizar vendas existentes.
