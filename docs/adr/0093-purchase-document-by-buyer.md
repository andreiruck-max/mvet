# ADR 0093 — Identidade da compra pelo comprador

A referência (fornecedor, documento, série) e a chave de reenvio pertencem ao
CNPJ comprador. Um número repetido entre CNPJs não mistura as notas e um reenvio
continua idempotente dentro da empresa. Identidade do comprador é imutável em
notas, linhas e parcelas. Uma NF do Bling só pode ser vinculada a uma compra
do CNPJ da conexão. Isso não autoriza usar o mesmo XML para dois destinatários.

As listas, detalhes, ações, relatórios por fornecedor, DRE, indicadores e
exportações individuais selecionam o comprador no servidor. A base pode
representar um rascunho manual secundário de homologação, com seus itens e
vencimentos. O bloqueio operacional permanece no serviço e no banco: a empresa
secundária ainda não confirma, recebe, vincula NF externa nem gera título.
O estado inativo da Agro não muda. Depósitos, fornecedores e SKUs são compartilhados.

No laboratório, validar duas referências iguais do mesmo fornecedor e com a
mesma chave de reenvio em CNPJs diferentes. Conferir que a confirmação da
Mercadovet cria somente seu título e seu movimento. URLs e arquivos individuais
não revelam o rascunho do outro comprador. O retorno à migration 0009 é seguro
com apenas os dados legados. A presença de rascunhos secundários impede esse
retorno; restaurar a cópia de homologação anterior, sem reatribuir documentos.
