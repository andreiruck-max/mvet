# ADR 0013 — Fontes e limites dos relatórios gerenciais
Data: 17/09/2026. Estado: aceito.

## Contexto
O usuário quer a leitura das planilhas: vendas tabulares, quadros diários de caixa e parcelas a pagar. As fontes já são transacionais. Datas de pagamentos não podem substituir competência; retenções financeiras podem já estar nos custos da venda.

## Decisão
Relatórios read-only em apps/reporting, agregados SQL Decimal e paginação. Sem novas tabelas/migrations de dados: modelos e permissões existentes são suficientes. Transação/mutex comum durante relatório gerencial para consistência de múltiplas consultas. Filtros limitados a 366 dias, caixa em blocos de 14 dias, vendas/parcelas em páginas de 30 registros; totais independentes da página.

DRE combina Sale confirmado, Expense ativo e natureza histórica. Título financeiro manual não legado usa data de origem como competência (instruída na tela/documentação), nunca a data de pagamento do principal. Juros adicionais reconhecidos na apuração em liquidação; estorno na data efetiva. Campos de principal/vínculos impedem que pagamento de despesa, compra ou venda repita resultado.

Abatimentos de liquidação não têm natureza suficientemente detalhada: podem representar taxas já consideradas na venda. Títulos manuais operacionais também não substituem Expense. Ambos aparecem como pendência; resultado parcial, sem adivinhação. Depreciação/amortização não implementadas ficam explícitas no nome do subtotal. Canal não recebe rateio arbitrário de despesas comuns; exibe contribuição.

## Consequências
Dashboard tem tabelas e atalhos com período preservado, e posições atuais de estoque/caixa claramente identificadas. API de indicadores não concede bancos/DRE. Usuário precisa registrar corretamente competência e distinguir juros adicionais de valores já apropriados. Classificação de abatimentos, apropriação diária de juros, fechamento imutável de períodos e depreciação são evoluções separadas. Relatórios refletem correções auditadas atuais.
