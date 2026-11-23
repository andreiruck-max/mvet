# ADR 0085 — Aritmética interna de estoque por proprietário

O saldo passa a ter unicidade por empresa, produto e depósito. Removem-se somente
as restrições temporárias de empresa principal de StockBalance, StockOperation e
StockMovement. Nenhuma linha histórica é reescrita. O mesmo SKU pode ter duas
posições patrimoniais no mesmo local; Product mantém o agregado físico informativo.

As primitivas internas _apply e _value_out calculam pelo proprietário da operação.
Os comandos públicos continuam bloqueando empresas secundárias; Company mantém a
restrição de secundárias inativas. O chamador interno responde pela autorização,
transação e lock de domínio/produto. Não há nova rota nem autorização implícita.

Testes sintéticos exercitam A/B/C: déficit por venda em cada sentido, duas pernas
de mudança de propriedade sem nova saída física e compra externa com média própria.
Uma referência provisória explícita precede a venda sem estoque; o custo da outra
empresa nunca é adotado silenciosamente. Falha na segunda perna reverte ambas.

Isto NÃO implementa o documento IntercompanyOperation, dívida de origem, formação
de preço, obrigações financeiras ou integração Bling. As pernas dos testes são
fixtures internas, não um serviço de fornecimento disponível ao usuário. Esses
fluxos e o isolamento das consultas legadas devem preceder a ativação da Agro.
A reversão da migration só é possível sem posições secundárias; não executar em
base operacional nem apagar histórico para viabilizar rollback.
