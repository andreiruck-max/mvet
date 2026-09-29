# ADR 0023 — Compras Bling, vendas por canal e caixa projetado

Aceito em 28/09/2026 por solicitação do usuário.

## Vendas
Relatório HTML com 50 vendas por página, agrupadas por canal, cabeçalho compacto e tabela responsiva sem rolagem horizontal. Composição financeira expansível preserva todos os valores; exportações mantêm as colunas completas. Totais de cada grupo abrangem todas as páginas do filtro. Cartões do topo mostram receita e contribuição das confirmadas de todos os canais no período, independentemente do filtro de canal/NF/situação. Custos e margens respeitam permissões no servidor e na apresentação; rascunhos/canceladas continuam identificados na referência e excluídos dos totais.

## Compras
Fila separada de NF-e de entrada (GET /nfe, tipo=0; situação 7 registrada ou 5 autorizada; consulta de canceladas 2 para divergências). Só notas existentes no Bling são consultadas; não há manifestação de destinatário/consulta SEFAZ automática nem escrita fiscal.

Contrato oficial consultado em 28/09/2026: https://developer.bling.com.br/build/assets/openapi-BVqLYFZn.json, NotasFiscaisDadosGetDTO, NotasFiscaisContatoDTO e NotasFiscaisParcelaDTO. Dados utilizados: itens/quantidade/valor/unidade/CFOP, contato nome/documento, valorFrete, valorNota, parcelas data/valor. Desconto não é documentado no retorno; iniciar zero e conferir manualmente. Não derivar descontos/impostos por diferença. O preço de aquisição da linha pode pré-preencher o rascunho de compra; nunca copiar custo médio de Bling nem modificar CMV histórico de vendas.

Chave de entrada de terceiros identifica fornecedor, não a própria empresa. Validar número/série/chave, fornecedor selecionado pelo documento e declaração explícita da destinatária/finalidade normal/unidades. Bloquear CFOPs não identificados como aquisição/venda de mercadoria, inclusive remessas/transferências/devoluções. Finalidade diversa de normal bloqueia; ausente requer a declaração. Conversões de unidade/embalagens não são automáticas. Seleção de produto é explícita e não grava alias global por código de fornecedor (códigos podem colidir entre fornecedores).

Importação cria somente rascunho editável, usando o serviço de compras. Conferir composição e reconciliar exatamente com o total fiscal. Parcelas fornecidas são editáveis; ausentes podem ser completadas na edição do rascunho. Confirmar compra cria obrigações, receber fisicamente movimenta estoque/custo local, baixar pagamento movimenta caixa. Identificador externo/chave são únicos; vínculo e snapshot de aprovação são protegidos no PostgreSQL, inclusive após cancelamento. Reconsulta não sobrescreve compra local; divergências ficam sinalizadas. Consulta exige fetch_bling + operate_purchases; importação de rascunho exige operate_purchases; confirmar/receber/pagar preservam permissões próprias.

## Caixa
Baixa antecipada usa data efetiva (até hoje), não data de vencimento. Saldo pago deixa a previsão; resto permanece. Estorno reabre principal; reagendamento altera previsão; lançamentos retroativos recalculam saldos posteriores. Não marcar saída futura como dinheiro já movimentado.

Total consolidado da empresa inclui pendências sem conta bancária na projeção, explicitamente identificado. Quadros de cada banco continuam excluindo valores sem alocação. Resumo considera fim do período completo, independentemente da paginação diária. Painel de pagamentos pendentes permite abrir baixa/reagendamento, incluindo vencimentos futuros. Sem alterações nos lançamentos existentes.
