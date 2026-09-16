# ADR 0010 — Compromisso, recebimento e rateio de compras
Estado: aceito. Data: 16/09/2026.

Uma compra não representa nem uma despesa integral na DRE nem um pagamento. Separar DRAFT, ORDERED, RECEIVED e CANCELLED. Parcelas pertencem ao compromisso confirmado e não geram nova compra. Liquidações integram o módulo financeiro na Fase 5; a dependência da issue de compras é de integração financeira, não impedimento para registrar compromissos.

Recebimento integral numa operação atômica gera PUR_RECEIPT e valores alocados por item. Quantidades por estoque, média global por produto. Rateio proporcional ao subtotal monetário de cada linha; maiores restos em centavos conservam exatamente o total. Unitário seis casas não será multiplicado de volta para valorizar a entrada. Sem base monetária positiva, custos adicionais não podem ser distribuídos silenciosamente por quantidades de unidades incompatíveis.

Compra recebida não pode ser editada. Cancelamento integral somente quando não houver operações efetivas posteriores nos produtos, restaurando snapshots em ordem inversa; isso evita valor residual ou custo distorcido após vendas. Estorno genérico do estoque rejeita PUR_RECEIPT/PUR_RETURN, assim como operações de venda. Transferências seguem disponíveis e devem ser revertidas antes de cancelar o recebimento anterior, quando seguro.

Recebimento parcial, devoluções parciais e ajustes de documento confirmado serão futuros fluxos próprios. Compromissos já pagos exigirão estorno financeiro antes do cancelamento, ao implementar a Fase 5.
