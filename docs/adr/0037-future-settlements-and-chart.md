# ADR 0037 — Baixas futuras e plano Mercadovet

Solicitação explícita de 10/10/2026 substitui a proibição de data futura para liquidações do ADR 0011.

## Baixas futuras
O operador pode registrar uma baixa em data futura. O principal fica reservado/baixado imediatamente, impedindo pagamento duplicado; a parcela aparece como Baixa futura. A operação imutável continua POSTED (registro confirmado no MVet), mas a apresentação é Registrada para data futura. Isso não agenda um pagamento no banco.

Realizado filtra data <= hoje. A projeção inclui a operação futura na data efetiva, além apenas do principal restante do título. No dia, a mesma operação passa automaticamente a compor o realizado pela consulta, sem job ou segundo lançamento. Juros/descontos usam a mesma regra de competência da liquidação e não duplicam a despesa de origem.

Cancelar uma baixa ainda futura gera contraparte na data original e reabre o principal agora, sem crédito fictício hoje. Data fornecida no formulário de estorno é substituída pela original nesse caso. O histórico conserva ator/data de criação. Após a data efetiva, estorno segue a regra normal. Transferências realizadas e lançamentos avulsos mantêm as validações anteriores.

## Plano de contas
Comando install_mercadovet_chart, chamado pelo atualizador Windows após migrations, instala configuração aditiva e idempotente. seed_key identifica cada categoria. Códigos ocupados com outra estrutura são preservados e o novo grupo recebe código livre. Não altera snapshots, classificações, regras nem valores existentes. Sem lançamentos financeiros na instalação.

Plano baseado no anexo do usuário: financiamento de veículos foi separado em principal (passivo, fora da DRE) e juros financeiros; benfeitorias capitalizáveis ficam em ativo, manutenção fica operacional. Grupo 90 admite naturezas patrimoniais diferentes nos filhos. Pendente tem snapshot NONE, deixando resultado parcial. Tributos/taxas/comissões já registrados na venda não devem ser relançados em Despesas. A instalação não gera automaticamente despesas por impostos das vendas.

Depreciação/amortização manual é natureza própria: Expense sem título, reconhecida por competência abaixo do EBITDA, sem caixa. Não gera recorrência financeira. Correções de classificação não podem transformar despesa com título em depreciação ou vice-versa; cancelar e registrar corretamente. Cancelamento sem título mantém auditoria e histórico imutável. Snapshot e constraint protegem a exceção sem obrigação financeira.

## Apresentação e exportação
Cartões de vendas/estoque: total primeiro, demais em valor decrescente. Ocultar valores dos cartões persiste localmente no navegador; não é controle de acesso nem remove valores das tabelas/exportações.

Exportação de vendas ignora canal/página por padrão, preservando período, NF e situação. scope=channel mantém filtro explicitamente quando necessário. Excel contém vendas completas, resumo por canal e abas por canal; PDF contém resumo e seções por canal, com produtos e deduções na mesma linha da NF. Permissões de custo e margem continuam aplicadas na projeção. Limites explícitos 10.000 linhas Excel/2.000 PDF nunca truncam silenciosamente.
