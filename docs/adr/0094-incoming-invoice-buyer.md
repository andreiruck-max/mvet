# 0094 — Identidade da compradora na NF-e de entrada

A chave de uma NF-e emitida pelo fornecedor identifica o emitente. Para atribuir
a compra a um CNPJ, ler o destinatário no XML correspondente à mesma chave e
comparar com a conexão da empresa. Em NF de entrada de emissão própria, a
compradora é a emitente e a direção no XML deve ser de entrada. O destinatário
pode ser o fornecedor. Se cadastrado, o CNPJ local deve coincidir com a conexão.

Uma divergência conhecida bloqueia rascunho, confirmação e recebimento, sem
salvar itens nem dados de contato de outra empresa. A fila guarda apenas a
identificação da nota e o resultado. Falha temporária de leitura do XML não
apaga o bloqueio. Uma nova leitura identificando a compradora permite prosseguir.
Operações anteriores e o snapshot aprovado não sofrem estorno automático.
Sem prova de divergência e sem XML identificável, permanece a conferência assistida
do 2.0. A checagem da compradora independe da apuração de descontos ou impostos.

Uma mesma chave só pode aparecer uma vez por conexão de entrada. Assim uma
consulta no CNPJ incorreto não reserva a chave da conexão correta. As conexões
secundárias e o acesso ao Bling real continuam desativados no laboratório.
