# ADR 0062 — Compra com tributos fiscais por item e ST/DIFAL de entrada por NCM

Aceito para desenvolvimento no MVet 3.0 (19/11/2026). Complementa ADR 0032 (desconto por item), ADR 0052 (frete externo) e a exigência multiempresa (empresa compradora e Bling próprios).

## Problema

A composição fiscal de notas interestaduais pode conter IPI no valor da NF e ST/DIFAL recolhidos separadamente pelo destinatário. Ratear um único valor adicional por toda a nota desloca custos entre SKUs e distorce custo médio, estoque e CMV. O valor dos títulos do fornecedor **não** deve incluir imposto de entrada pago a outro credor.

## Regras

1. `PurchaseItem` registra NCM, IPI da linha **incluído no documento fiscal**, ST de entrada **fora da NF** e DIFAL de entrada **fora da NF**, todos em centavos e sem inferência por diferença de totais.
2. O preço unitário e desconto do item constituem a base líquida `quantidade × preço − desconto da linha`. Desconto geral e frete da própria NF seguem rateio proporcional pelos valores líquidos (ADR 0032). O IPI integra o valor da NF **somente** na sua linha, não se distribui por outros produtos.
3. Na revisão da importação Bling o operador informa ST e DIFAL apurados pela contabilidade por NCM (`NCM=valor`, uma linha por código). O serviço distribui o valor sobre os itens do MESMO NCM proporcionalmente à base líquida, pelo algoritmo de maiores restos; preserva soma exata em centavos e rejeita NCM desconhecido/duplicado ou base total zero com encargo positivo.
4. `Purchase.total` é a obrigação com o fornecedor: itens − descontos + IPI + frete e outros custos da NF. O total deve conciliar com `valorNota` informado pelo Bling, com precisão em centavos, sem imposto externo.
5. `Purchase.acquisition_total` acrescenta ao total do fornecedor o frete externo e a soma de ST/DIFAL de entrada. Cada `PurchaseItem.allocated_total` incorpora sua parcela de custo; itens `NONSTOCK` retêm seu próprio valor sem contaminar estoque de revenda. `landed_unit_cost` é derivado por quantidade com seis casas, mas movimentação usa valor alocado exato.
6. Os encargos ST/DIFAL de entrada **não** criam títulos a pagar ao fornecedor e **não** geram lançamentos bancários automáticos: a guia e seu pagamento pertencem ao financeiro/fiscal, com credor e vencimento próprios. Não criar dívida fictícia nem duplicar caixa.
7. O enriquecimento opcional e read-only do XML Bling fornece NCM e IPI por linha apenas quando a chave, itens, descontos, preços e totais fiscais são verificados. Falhas preservam a revisão manual. Não persistir URL assinada nem XML bruto. Nunca inferir IPI do delta entre valor bruto de produtos e valor da nota.
8. O NCM deve ser informado pelo XML confiável ou digitado/revisado. Se o XML validado trouxe NCM/IPI, uma divergência manual bloqueia a importação; reconsulta é necessária.
9. A compra confirmada conserva valores imutáveis; histórico de compras, custo médio e CMV de vendas passadas não é reprocessado.
10. No MVet 3.0 os dados fiscais seguem o CNPJ da compradora. Não compensar tributos ou custo entre empresas. Não alterar MVet 2.0/main nem banco de produção antes de aprovação específica.

## Caso de regressão NF 163303 Zebu (valores informados em 19/11/2026)

Valor bruto dos itens R$ 3.736,50, desconto R$ 186,82, IPI R$ 210,56, **NF R$ 3.760,24**; ST por NCM 85437092 R$ 510,82 e 85354010 R$ 23,52; DIFAL NCM 73121090 R$ 11,20. **Custo agregado R$ 4.305,78**.

Valores alocados por SKU, incluídos encargos: ZK50 R$ 834,00/5 = R$ 166,800000; ZK200 R$ 2.377,20/5 = R$ 475,440000; PPCR R$ 266,83/3 = R$ 88,943333; KIT RAIO R$ 145,83/5 = R$ 29,166000; FIO R$ 157,16/2 = R$ 78,580000; ARAME R$ 455,12/2 = R$ 227,560000; PORTEIRA R$ 69,64/2 = R$ 34,820000.

O valor unitário arredondado é informativo; a soma dos valores por linha é que deve fechar o custo total.
