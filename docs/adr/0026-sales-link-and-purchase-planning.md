# ADR 0026 — Vínculo por código, confirmação única e planejamento

Data: 07/10/2026. Decisão solicitada pelo proprietário; substitui a exigência de checkbox específico do ADR 0017.

Vendas Bling usam a unidade do produto MVet, com a quantidade externa inalterada. Unidade externa não participa da associação nem da elegibilidade. A interface seleciona o item da nota em vez de exigir digitação de código/unidade. Novos aliases usam unidade vazia como escopo por código; aliases antigos ficam preservados. Um vínculo explícito por código prevalece; aliases legados concordantes continuam válidos, divergentes exigem escolha explícita. SKU coincidente com outro produto e troca de vínculo canônico continuam bloqueados.

A ação Conferir e confirmar venda substitui a marcação adicional de finalidade. O aviso informa o significado da ação quando o campo externo está ausente. Serviço exige reviewed=True booleano; audita ator, finalidade ausente e ação. Finalidade recebida permanece intacta; finalidade conhecida não normal, situação inválida, remessas e devoluções continuam bloqueadas. Não há confirmação automática por consulta ou lote.

Estoque inicia com saldo positivo; filtro explícito positive=0 permite ver zerados, inclusive exportação. A pesquisa de produtos para vinculação continua independente desse filtro.

Planejar compra é consulta com permissões de estoque e compras. Considera produtos simples ativos por depósito; demanda usa saídas de venda não estornadas no período escolhido, incluindo componentes baixados em kits. Sugere max(mínimo, vendas / dias de histórico × cobertura) menos saldo e compras ORDERED a receber; resultado não negativo, arredondado para cima em quatro casas. Não converte embalagem nem gera pedido/financeiro. Não é previsão de vendas perdidas por ruptura.

Fora de linha apenas neste planejamento: saldo zero e última movimentação de quantidade registrada há pelo menos N dias (30 inicialmente). Usa horário de criação da operação, não data retroativa de competência. Estornos contam como movimentação; correções somente de custo não contam. Sem histórico não se presume idade e o produto permanece. Cadastro ativo e histórico contábil não são modificados. Filtros numéricos e depósito são lembrados na sessão. Sem alteração de schema ou migração de dados.
