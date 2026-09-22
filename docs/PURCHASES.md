# Compras e fornecedores — Fase 4
Implementação: `apps/purchases`. Operação manual; evidências de validação no pull request da fase.

## Uso
1. Compras → Fornecedores → Novo fornecedor. Razão social/nome obrigatório; CPF/CNPJ opcional, normalizado sem pontuação e único quando informado. Cadastro permite contato, telefone, e-mail, observações e inativação. Não há exclusão de fornecedor pela interface.
2. Nova compra: fornecedor, NF/documento e série, data, estoque de destino, desconto, frete e custos de aquisição.
3. Buscar produtos por SKU/nome e informar quantidade e preço unitário. Aceita produtos simples; kits virtuais são vendidos por composição, não comprados como estoque físico.
4. Adicionar parcelas e vencimentos. A soma deve fechar o total da compra. É possível salvar rascunho sem parcelas para conferir e completar depois.
5. Salvar e revisar os valores e rateios. Confirmar compra registra o compromisso; ainda não movimenta estoque ou caixa.
6. Ao chegar a mercadoria, informar data e confirmar recebimento integral. A entrada atualiza quantidade por local e custo médio global por produto, sem modificar vendas anteriores.
7. Para enviar mercadoria ao Full ou outro depósito: Movimentações → Movimentar estoque → Transferência → produto, origem, destino, quantidade e motivo. Link também disponível na compra recebida para quem tem permissão de estoque. Transferência conserva quantidade global, valorização e média.

## Valores e rateio
Subtotal de cada item = quantidade × preço unitário, arredondado HALF_UP em centavos. Total = soma dos subtotais − desconto + frete + outros custos de aquisição.
Ratear o total final proporcionalmente aos subtotais, em centavos, pelo método dos maiores restos; desempate pela ordem dos itens. A soma dos valores incorporados é exatamente o total da compra. O custo unitário com rateio tem seis casas e é informativo; o livro recebe o valor alocado exato, sem multiplicar de volta um unitário arredondado.
Itens gratuitos recebem valor zero. Se todos os subtotais forem zero, só é possível receber uma compra de total zero (sem parcelas). Custos positivos sobre base inteiramente zero exigem corrigir os valores dos itens.
Desconto não pode exceder os produtos. Juros de financiamento e multas não devem ser lançados como custo de aquisição: tratamento financeiro na Fase 5.

## Estados e integridade
- DRAFT: editável, sem estoque, parcelas apenas planejadas.
- ORDERED: valores/itens/parcelas congelados; obrigações pendentes; ainda sem estoque.
- RECEIVED: movimento PUR_RECEIPT ligado a cada item, atores/datas e snapshots preservados.
- CANCELLED: motivo, ator, horário e eventual PUR_RETURN; registros permanecem.
UUID evita criação repetida; revisão impede edição perdida; confirmação/recebimento/cancelamento são idempotentes. Documento/série únicos por fornecedor, inclusive canceladas. Números normalizados removem zeros à esquerda.
Transações usam o mesmo mutex e ordem de locks do estoque/vendas. Triggers PostgreSQL bloqueiam alterações indevidas dos históricos e valores das parcelas. Não há edição transacional pelo admin.

## Datas e cancelamento
Data da compra entre o corte e hoje. Recebimento entre a data da compra e hoje e não anterior a movimentos já registrados nos produtos. Não reconstruir custo retroativamente.
Rascunho ou compra confirmada podem ser cancelados com motivo, cancelando suas parcelas. Compra recebida só pode ser cancelada se o recebimento ainda for a última operação efetiva dos produtos. Transferências, saídas ou novas entradas posteriores bloqueiam o cancelamento; estornar operações posteriores quando tecnicamente seguro antes de cancelar. Não apagar ou recalcular vendas para forçar cancelamento.
A reversão restaura quantidade, valor e média anteriores em ordem inversa dos movimentos. Recebimento parcial e devolução parcial são evoluções futuras.

## Parcelas e financeiro
PurchaseInstallment guarda número, vencimento, valor, observação e status. Vencida é apresentação derivada da data; não depender de tarefa noturna. Compromissos de rascunhos não entram nos totais abertos. Parcelas não multiplicam o total comprado.
**Pagamento integrado na Fase 5.** Confirmar compra cria título por parcela; abrir o vínculo permite marcar como pago parcial/integralmente, escolhendo conta/data e diferenças explícitas. Situação e saldo pendente derivam do título. Cancelamento da compra exige estornar liquidações ativas primeiro. Compras anteriores ao corte com pendências devem ser lançadas como abertura financeira, não como nova aquisição de estoque. Ver FINANCE.md.

## Consulta e permissões
Listagens paginadas, pesquisa documento/SKU/nome, fornecedor, estoque, estado, períodos de compra e vencimento, pendentes/vencidas. Datas de vencimento são filtradas sobre a mesma parcela.
`operate_purchases`: cadastros, compras, compromisso, recebimento, cancelamento; consulta de valores individuais necessários à operação. Não concede margem, DRE, bancos ou custo médio global. Transferência exige `operate_stock`.
`view_purchase_reports`: totais, quantidade de compras, ticket médio, última compra, obrigações abertas e histórico de preços recebidos por fornecedor, sem escrita. API `/api/v1/fornecedores/<id>/resumo/` exige essa permissão.
Perfis iniciais ADMINISTRADOR e FINANCEIRO recebem as duas permissões; GERENCIAL recebe relatórios. Migration adiciona somente essas novas permissões aos perfis existentes; demais concessões são preservadas. VENDAS_OPERACIONAL e ESTOQUE não ganham acesso a compras.

MVet 1.5: recebimento pondera custo médio apenas do depósito recebedor; transferência conserva valor e pondera destino. Cancelamento preserva valor original e referência local de custo. Ver ADR 0019.
