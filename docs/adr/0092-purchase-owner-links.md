# ADR 0092 — A compra, o recebimento e a obrigação pertencem ao mesmo CNPJ

A conta prevista, a operação de recebimento ou de estorno e a própria compra
têm o mesmo proprietário. Item, movimento e categoria sem estoque também;
a parcela herda a empresa da compra e o título conserva a empresa da parcela.
Produto, fornecedor e depósito são identidades compartilhadas.

A migration 0009 de compras adiciona chaves estrangeiras compostas no PostgreSQL.
A combinação (empresa, id) do registro referenciado é única. Assim, inclusive
um UPDATE direto precisa respeitar o CNPJ nos dois lados. Conta, movimento e
estorno ausentes continuam permitidos. As restrições anteriores de histórico,
transição de empresa e unicidade de títulos permanecem ativas. O rascunho e o
reenvio da importação verificam o contexto antes de devolver o documento.

Validar em PostgreSQL isolado: confirmar uma compra com duas parcelas gera dois
títulos e nenhum débito; tentar vincular um movimento de outra empresa, mesmo
com SKU, preço, quantidade e depósito iguais, deve falhar. Índices e validação
de FKs exigem locks de DDL: medir o tempo em cópia representativa antes de
qualquer implantação. Uma divergência existente interrompe a migration,
identificando a restrição; não é corrigida automaticamente. Reverter 0009
remove apenas as novas chaves, sem alterar notas ou movimentos.
