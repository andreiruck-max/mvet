# ADR 0029 — conferência por série e vendas com estoque negativo

Estado: implementado; integração à main autorizada após validação. Instalação local aguarda OK do usuário ao fim do pacote.

## Decisão solicitada
Calendário nativo abre ao clicar em qualquer campo de data quando o navegador oferece showPicker; digitação e ícone continuam disponíveis. Fila de notas de venda Bling ordenada numericamente por série e número, com filtro de série preservado na paginação e no escopo assinado das ações em massa. Exibir valor fiscal e somente nome do cliente (contato.nome), sem criar cadastro de cliente ou conservar documentos/endereço. Atualização apenas do nome não gera divergência comercial em venda importada. Notas antigas recebem o nome na próxima consulta ao Bling.

Regra tributária sugerida entre regras ativas válidas para a data comercial da nota (hoje numa nova venda manual). Prevalece início de vigência mais recente, desempate por ID. POST e edição de rascunho preservam seleção explícita. Sem regra válida, nenhuma é inventada; validação de confirmação permanece.

O usuário autorizou confirmar vendas com estoque negativo e escolheu expressamente o último custo conhecido do depósito. Não se usa custo de outro depósito. Sem histórico local, confirmar exige primeiro informar referência pela operação Correção de custo. Zero explicitamente registrado é custo válido, inclusive bonificação. Saídas avulsas, transferências e kits avulsos continuam exigindo saldo; confirmação de venda inclui componentes de kits.

## Valorização e resultado
Saldos locais podem ter quantidade/valor negativos, com média não negativa. Quantidade zero exige valor zero. Product consolida quantidades e valores assinados; seu custo informativo pondera apenas saldos positivos ou, se inexistentes, os negativos. CMV sempre usa o depósito.

Venda consome saldo e último custo local sob os mesmos locks e transação. Reposição que cobre déficit mantém a média da parcela ainda negativa e valoriza eventual sobra pelo custo da entrada. A diferença entre valor de origem e variação do estoque fica em StockMovement.cost_variance, imutável, sem reescrever movimentos anteriores ou CMV. Exemplo: déficit de 2 a R$ 5 e entrada de 3 a R$ 7 deixam 1 a R$ 7, com diferença de R$ 4 reconhecida no resultado.

Diferença positiva reduz resultado, negativa aumenta. DRE/indicador de resultado/exportações somam a diferença como despesa operacional da empresa na data do movimento, sem rateio presumido por canal e sem gerar caixa ou títulos. Margem individual da venda continua pelo CMV histórico. Bonificação pode produzir diferença negativa. Reversão cronologicamente válida restitui exatamente quantidade, valor, média e diferença originais. Cancelamento de venda devolve custo histórico; recuperação preserva CMV e registra eventual diferença entre esse custo e o estoque corrente. Recuperação continua master-only e com vínculo imutável.

## Compatibilidade
Migrations aditivas de schema: relaxar constraints de quantidade/valor agregados, substituir constraints locais por coerência de sinal e acrescentar cost_variance com zero para registros existentes. Nenhuma venda real é editada. Triggers de imutabilidade permanecem; variância não permite editar livro existente. Downgrade para constraints antigas é incompatível enquanto existirem saldos negativos — não fazer rollback de schema sem tratamento explícito.

## Validação
Testes de reposição parcial/total, custo maior/menor, bonificação, ausência de referência, depósitos com saldo líquido zero, cancelamento/recuperação, reversão de entrada/compra e duas vendas concorrentes. Conferência do livro por check_inventory. Testes de nome allowlisted, divergência real, filtro/ordem/escopo em massa e regras tributárias por vigência. Chromium cobre clique no campo de data, filtro, cliente, valor, regra sugerida e confirmação com saldo negativo.
