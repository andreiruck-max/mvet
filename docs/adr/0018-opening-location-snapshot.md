# ADR 0018 — Posição inicial por depósito na data do relatório

Um relatório atual de estoque não representa a posição histórica no corte da empresa.
O novo importador restrito a SKUs inexistentes registra uma operação OPENING por
produto na data explícita do relatório (entre corte e hoje), com um movimento por
depósito. Não altera o corte da empresa nem a abertura manual/XLSX existente.

Os valores originais de cada depósito compõem o custo médio global ponderado.
Saldo zero conserva apenas custo de referência e não substitui a média de saldo
positivo. Quantidades por local e valores dos movimentos são preservados.

A carga é atômica, auditada e idempotente por conteúdo normalizado. SKU existente,
depósito inativo, saldo negativo, duplicidade ou erro de formato bloqueiam tudo.
Não é conciliação/substituição de estoque existente. Não gera caixa ou DRE.

Notas/vendas anteriores já refletidas no relatório não devem baixar esse estoque
novamente. Os bloqueios cronológicos do domínio continuam ativos. A simulação
na instalação de destino é obrigatória antes da aplicação operacional.
