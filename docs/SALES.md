# Vendas — contrato para Fase 3
Estado: especificado, ainda não implementado.
Cadastro rápido: data, NF/série, canal, valores e vários itens pesquisados por SKU ou nome. Canal configurável. Quantidades informadas; custo snapshot e CMV calculados na confirmação.

## Estados
Rascunho não baixa estoque. Confirmação atômica cria snapshots e movimentos uma única vez. Cancelamento registra motivo e reverte movimentos efetivos. Venda não é apagada. Recebíveis/liquidações vinculados exigem tratamento explícito antes do cancelamento.

## Resultado
Receita operacional = produtos − desconto + frete recebido.
Margem de contribuição = receita operacional − CMV − frete pago − taxas − imposto − DIFAL − comissão − outros custos variáveis.
Margem % = contribuição / receita operacional. Receita zero retorna percentual indefinido, não divisão por zero.
Alertas usam limite configurado; negativo é destacado. Não chamar margem de venda de EBITDA.

## Impostos
Regra com nome, vigência, alíquota, base. Snapshot por venda. Override com motivo auditado. Não presumir alíquota atual da empresa.

## Histórico e corte
Data comercial e horário físico do estoque separados. Vendas anteriores ao corte não serão importadas automaticamente. Não confirmar venda histórica com CMV atual sem explicitar a política de lançamento retroativo.
Testes: várias linhas, kit, snapshots após compra posterior, descontos/fretes/taxas/impostos, cancelamento e autorização de custos/resultados.
