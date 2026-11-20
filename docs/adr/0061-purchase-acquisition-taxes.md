# 0061 — MVet 2.0: composição fiscal, custo por linha e obrigações externas

19/11/2026. Alteração exclusiva do 2.0, baseada na revisão da PR 96, sem integrar a branch multiempresa.

O valor da NF/parcelas do fornecedor e o custo incorporado são distintos. IPI, ST/FCP-ST da NF e II/IPI devolvido pertencem à própria linha. ST/DIFAL externos são informados por NCM e distribuídos em centavos por maiores restos sobre quantidade × preço − desconto individual, apenas entre linhas do mesmo NCM. Desconto geral não modifica essa base. Frete externo mantém o rateio exclusivo sobre estoque. Frete/seguro/despesas identificados no XML permanecem em suas linhas; somente o restante dos encargos gerais é rateado.

Crédito tributário recuperável é informado por item após revisão contábil, reduz custo sem reduzir obrigação do fornecedor ou fisco. O sistema não determina regime tributário nem direito a crédito. Confirmar compra com tributos/créditos exige declaração explícita de revisão. Linhas sem estoque preservam sua categoria e custo líquido; bonificações continuam sem obrigação e valorização.

XML é validado contra chave, códigos, quantidades, preços e total da API. A projeção guarda componentes, não XML nem URLs assinadas. NCM e IPI são vinculados ao item; totais e reconstrução fiscal são mostrados. Diferenças e componentes fiscais não classificados bloqueiam a importação normal, sem ajuste residual. ICMS desonerado não é convertido automaticamente em dedução/custo: exige regularização documental. Sem XML confiável permanece conferência manual com reconciliação exata. Não presume descontos ou tributos pela diferença.

Prévia usa o mesmo serviço dentro de transação revertida: não persiste fornecedores, produtos, compra, auditoria, títulos ou estoque. Importar salva rascunho; confirmar gera apenas parcelas do fornecedor; receber usa valores alocados exatos no depósito, sem reconstruir o total pelo custo unitário de seis casas nem alterar CMV anterior.

Após confirmar, ação explícita registra obrigação de ST ou DIFAL externo com credor, vencimento e conta. Um vínculo único compra/tipo impede duplicidade. Classificação patrimonial evita despesa duplicada; liquidação usa financeiro existente. Nunca paga ao importar. Antes de cancelar a compra, revisar/cancelar separadamente obrigações fiscais já geradas. Título fiscal cancelado permanece no vínculo; eventual recriação exige revisão explícita futura, não automática.

Parcela de compra sem liquidação pode ser cancelada individualmente pelo financeiro, com permissão de cancelamento, motivo e auditoria. Não altera contrato, valor fiscal, demais parcelas, estoque ou CMV. Baixas ativas impedem cancelamento. Cancelamento posterior da compra ignora parcelas já canceladas, preservando a proteção PostgreSQL.

Migrations aditivas 0008/0009: campos iniciam zerados/falsos, sem reprocessar compras antigas. Triggers existentes baseados em JSON protegem automaticamente os novos componentes após confirmação. Nenhuma migration do 3.0 ou operação de produção.
