# 0095 — NF de terceiros: valor devido e custo por produto no CNPJ comprador

Manter o SKU compartilhado não torna globais seus custos, impostos ou créditos.
Na consulta da empresa, confrontar chave, quantidade, preço, código e desconto
com o XML. Campos fiscais não se aplicam às vendas. O IPI, a ST e os custos
atribuídos a um item não são transferidos a outro. A diferença entre vProd e
vNF não é um imposto. Exibir valor fiscal, reconstrução e diferença; impedir
a importação enquanto houver divergência, sem ajuste automático. Um download
posterior sem XML não apaga a divergência conhecida.

ST e DIFAL externos distribuem-se somente entre os produtos de igual NCM;
a base é o valor bruto da linha menos o desconto individual, independentemente
da quantidade de outras linhas. Arredondar por maiores restos em centavos,
com desempate pela posição na nota. Os créditos recuperáveis informados por
item reduzem o custo, sem reduzir a obrigação com o fornecedor. O frete
externo se aplica aos itens de estoque e não integra as parcelas. O recebimento
lança o total exato da linha no livro da compradora. Bonificações permanecem
sem títulos e as vendas já confirmadas conservam o CMV original.

Regressão sintética da NF 163303: R$ 3.736,50 − R$ 186,82 + R$ 210,56 =
R$ 3.760,24 na NF; ST externa de R$ 534,34 e DIFAL externo de R$ 11,20
levam a R$ 4.305,78 de aquisição, assumindo créditos recuperáveis nulos.
Não há consulta ao Bling nem reprodução do XML real no teste. A prévia usa
a mesma transação da importação e a reverte integralmente, incluindo novos
fornecedores, produtos e auditoria que só cabe ao ato definitivo.
