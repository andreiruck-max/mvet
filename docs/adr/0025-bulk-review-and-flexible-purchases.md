# ADR 0025 — Revisão em massa, compras mistas e bonificações

Aceito em 06/10/2026 por solicitação do usuário. Complementa ADRs 0010, 0023 e 0024.

## Filas Bling

Selecionar notas marcadas, a página ou todas as notas não importadas do filtro (até 5.000 por lote). Prévia identifica a quantidade, ação e campos modificados. Seleção assinada, vinculada ao usuário e às revisões, expira após uma hora. A aplicação é atômica: nota alterada, importada ou ausente invalida o lote inteiro. Notas adicionadas após a seleção não entram no lote. POST/CSRF e permissões individuais permanecem obrigatórios.

Ignorar/rejeitar e reabrir são reversíveis, auditados e locais. Não apagam histórico nem movimentam estoque/financeiro. Edição em massa altera sugestões persistentes de canal/depósito (vendas) e depósito/tipo de entrada/destino dos itens/categoria (compras). Não aprova venda nem confirma compra em lote; conferência individual continua necessária. Reconsulta externa preserva decisões locais. Notas já vinculadas não são editáveis pela fila.

## Itens de compra

Padrão continua movimentar estoque. Cada item pode ser marcado como somente financeiro, sem exigir cadastro de produto. Descrição externa é preservada. Quantidade, preço e subtotal permanecem no documento e no total integral a pagar. Descontos, frete e outros custos são rateados entre TODOS os itens; a parcela atribuída aos itens sem estoque não é repassada ao custo dos itens estocáveis.

PurchaseItem separa `allocated_total` (estoque) de `nonstock_total` (sem estoque). A soma de ambos, de todos os itens, conserva o total financeiro da compra. Itens sem estoque não geram movimento. Documento exclusivamente financeiro pode concluir recebimento sem criar operação vazia de estoque. Cancelamento preserva as proteções sobre pagamentos e reverte apenas movimentos existentes.

Categoria analítica opcional por item sem estoque, com snapshot do caminho/natureza. Exige `operate_expenses`. A confirmação reconhece o valor operacional/financeiro na DRE pela data da compra, uma única vez, sem criar outro Expense ou outro título. Sem categoria fica explicitamente a classificar. Naturezas patrimoniais não afetam resultado. Uso pessoal deve ser classificado explicitamente em categoria patrimonial apropriada, nunca presumido como despesa operacional. O detalhe da compra é a origem desse reconhecimento; a listagem do módulo Despesas continua contendo seus lançamentos próprios. Correção de item confirmado continua exigindo cancelamento e novo lançamento, sem reclassificação silenciosa.

## Cadastro durante importação

Código externo vazio não impede compras. Para estoque, exige selecionar produto ou cadastrar novo SKU, nome local editável e unidade. Cadastro e rascunho são uma transação, com permissões `manage_products` e `operate_stock`; erro posterior desfaz ambos. Não cria vínculo global por código de fornecedor. Unidade local prevalece, sem conversão. Reenvio da nota vinculada não duplica cadastro ou compra.

## Bonificação

Escolha explícita `BONUS`, compatível com CFOP x910 e finalidade fiscal normal (ou declaração humana específica quando ausente). Outras remessas, transferências, devoluções e notas canceladas continuam bloqueadas. Não liberar CFOP arbitrário sob a justificativa de bonificação.

Preserva preços/subtotais e total fiscal no documento de origem. Total financeiro e custos incorporados são zero; não gera parcelas/títulos/pagamentos. Parcelas externas são desconsideradas pela UI nesse modo. Não aceita frete, desconto ou custos pagos embutidos nessa entrada gratuita: registrar cobrança separada. Recebimento aumenta quantidade no depósito escolhido sem aumentar valor; pondera custo médio atual e não recalcula CMV histórico. Não altera nem cancela a compra que originou a bonificação.

## Migração e implantação

Campos novos têm padrões equivalentes ao comportamento anterior: compras normais, todos os itens estocáveis, sem classificação nem valores adicionais. Não reescreve movimentos, parcelas, dados fiscais ou custos históricos. Triggers existentes continuam protegendo os novos campos após confirmação. Implantação local fica adiada para o pacote solicitado pelo usuário; não executar limpeza automática de dados reais durante a atualização.
