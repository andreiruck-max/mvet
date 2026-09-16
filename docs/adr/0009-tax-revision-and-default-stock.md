# ADR 0009 — Alíquota retroativa auditada e estoque padrão
Estado: aceito por solicitação explícita do usuário em 16/09/2026.

## Mudança de política tributária
A regra anterior impedia toda alteração de imposto confirmado. O usuário passou a exigir edição da alíquota com data de início e recálculo retroativo.

Cada edição cria TaxRateChange imutável (regra, alíquota, base, início, ator, motivo, horário). Para cálculo na data comercial, vale a maior data de início não posterior à venda; em empate, a edição mais recente. A configuração inicial da regra permanece como base para datas anteriores às alterações.

Se o início for anterior a hoje, recalcular vendas confirmadas dessa regra desde o início até a próxima vigência já cadastrada. Vendas com imposto manual e canceladas são preservadas. Se o início for hoje ou futuro, nenhuma venda já confirmada é alterada; próximas confirmações usam a vigência aplicável à data comercial. Rascunhos calculam somente na confirmação.

O recálculo altera exclusivamente imposto aplicado e snapshot tributário, criando SaleTaxRevision imutável com valores/snapshots antes/depois. A margem individual se ajusta por derivação. CMV, itens, estoque, taxas e demais dados permanecem intactos. A operação inteira é atômica, autorizada por manage_configuration, sob o mutex compartilhado, com auditoria. Revisão da regra rejeita edição concorrente obsoleta.

PostgreSQL só permite essa exceção na venda confirmada quando existe revisão imutável correspondente ao antes/depois e ao identificador de alteração declarado pela transação. Outros updates históricos continuam bloqueados. A flag local é limpa ao final.

## Estoques
Company.default_stock_location é sugestão para novas vendas, nunca um nome hardcoded usado na regra de negócio. Usuário pode trocar antes da confirmação; rascunhos existentes conservam a escolha. Estoques podem ser adicionados/inativados. Trocar padrão antes de inativá-lo. Setup de instalação vazia cria Estoque Mercadovet (padrão) e Estoque Full, editáveis. Instalações com locais existentes são preservadas.

Saldos são separados por local, custo médio continua global por produto (ADR anterior). Baixa e cancelamento afetam o local escolhido/original. Não combinar silenciosamente saldos de locais diferentes para atender uma venda.

## Taxas extras
SaleExtraCost contém linhas nome/valor em reais (ex.: MDR), editáveis no rascunho, congeladas após confirmação. Soma armazenada em Sale.extra_costs_total, deduzida uma única vez da margem. Não repetir os mesmos valores no campo agregado Taxas. Não representa liquidação de caixa; financeiro será integrado posteriormente.
