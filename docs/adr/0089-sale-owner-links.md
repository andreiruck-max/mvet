# ADR 0089 — Vínculos empresariais de venda e consumo de estoque

Uma FK pelo ID garante que o cadastro existe, mas permite que um rascunho
aponte para uma regra tributária ou operação de estoque de outro CNPJ. Isso
passou a ser relevante quando essas tabelas admitiram empresas diferentes.

A migration 0023 valida no PostgreSQL as referências não nulas de Sale (canal,
regra, comissionado, operação de saída e estorno) e as duas referências de
SaleConsumption (item e movimento). Faz uma verificação dos registros existentes:
se encontrar inconsistência, falha na transação, sem corrigir o histórico.
Novos vínculos são conferidos na escrita. A titularidade dos pais é imutável
ou, no caso dos comissionados e itens, ainda limitada à principal. Ao liberar
esses cadastros para outro CNPJ, deve-se preservar essa titularidade.

A reversão remove somente as novas proteções. Não muda valor fiscal nem CMV,
não refaz estoque e não habilita vendas na empresa secundária.
