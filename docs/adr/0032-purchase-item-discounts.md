# ADR 0032 — Desconto específico de item e fornecedor na importação

Aceito em 09/10/2026, a pedido do proprietário. Complementa ADRs 0010 e 0025.

`PurchaseItem.discount` registra o desconto total da linha, em reais, não o desconto unitário. O subtotal bruto continua quantidade × preço, arredondado em centavos. A base líquida é subtotal bruto menos desconto daquele item. Desconto geral, frete e outros custos são rateados sobre as bases líquidas pelo método existente dos maiores restos. Não lançar novamente no desconto geral os descontos dos itens.

Total financeiro = produtos brutos − descontos dos itens − desconto geral + frete + outros custos. Valores de estoque e valores sem estoque somam exatamente esse total. Sem encargos gerais, desconto de um produto não altera a valorização dos demais. Impedir desconto negativo, desconto de item maior que seu bruto e desconto geral maior que a base líquida. Linhas totalmente descontadas têm base zero; não distribuir encargos sobre base inteiramente zero. Bonificação continua com entrada valorizada em zero e sem financeiro; a composição fiscal é conferida separadamente.

Importação e edição manual de rascunho apresentam o campo por linha; parcelas e total fiscal precisam fechar. Não presumir um desconto por diferença nem aplicar automaticamente percentuais não normalizados da API. Se o preço externo já for líquido, não repetir desconto. Campo novo inicia em zero: não reprocessa compras, movimentos, médias ou CMV históricos. Triggers de imutabilidade também protegem o novo campo nas compras confirmadas.

Na importação, o usuário pode selecionar fornecedor existente ou criar um com dados disponíveis no documento: nome, documento e, quando presentes, telefone, e-mail e nome fantasia. Campos são conferíveis/editáveis, mas documento deve corresponder à nota. Cadastro e rascunho são atômicos e auditados. Não sobrescrever fornecedor existente; CPF/CNPJ duplicado é bloqueado, devendo selecionar o cadastro existente. Exige `manage_suppliers` e `operate_purchases`. Reenvio de nota já vinculada não duplica fornecedor/compra. Não exige consulta externa adicional de contato.
