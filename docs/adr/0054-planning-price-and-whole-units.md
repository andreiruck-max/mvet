# ADR 0054 — Referência de compra e sugestões inteiras

Data: 09/11/2026.

Por solicitação do proprietário, o planejamento arredonda a necessidade positiva para cima em unidades inteiras, após descontar estoque e compras a receber. Substitui o arredondamento de quatro casas da ADR 0026 somente na sugestão; saldos, movimentos e valores históricos permanecem intactos. Não converte embalagens. Tela e cotação PDF/Excel usam a mesma quantidade.

Referência interna: último item de compra NORMAL RECEIVED, por data da compra (desempate pelo ID da compra e do item), em qualquer depósito, com compra e recebimento até a data da consulta. Exclui bonificações, canceladas, rascunhos e pedidos pendentes. Mostra preço unitário da nota antes dos descontos/rateios, fornecedor e data. Não é custo médio nem comprovação de pagamento. Sem referência, informa Sem histórico. Consulta em lote sem N+1; permissões existentes de estoque/compras preservadas.

Exportações não incluem preço histórico. Ao agrupar por fornecedor, acrescentam a coluna de fornecedor da última compra. Nenhum lançamento, pedido ou migração é criado.

Filtro opcional usa o fornecedor da última compra elegível, não qualquer fornecedor antigo. Inclui fornecedores inativos para preservar a referência e opção sem histórico. Aplica antes da paginação e dos totalizadores. Agrupamento mantém SKU dentro de cada fornecedor e sem histórico ao final; cabeçalho se repete quando o grupo continua na página seguinte. Filtro e organização persistem na sessão; selecionar Todos os fornecedores limpa o filtro.
