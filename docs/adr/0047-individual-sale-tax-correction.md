# ADR 0047 — Correção individual de imposto na venda
Data: 19/10/2026. Estado: aceito, a pedido do usuário.

Corrigir venda, exclusivo do master, admite manter o tratamento, definir alíquota individual (0–100%, quatro casas) ou definir valor monetário (inclusive zero). Somente o campo do modo escolhido é aplicado. Motivo obrigatório, revisão otimista e chave idempotente continuam no serviço existente.

A base da alíquota é a registrada no snapshot da venda, atualizada pelos valores corrigidos na mesma transação. Receita inclui ajuste gerencial quando essa é a base histórica. Sem base histórica, não se presume uma: permite somente valor direto. Não altera TaxRule/TaxRateChange nem outras vendas. Imposto/base/alíquota e tratamento são registrados no snapshot e no SaleCorrection antes/depois. Histórico mostra imposto e alíquota, mesmo se o valor arredondado não mudar.

Correção individual marca override no snapshot. Recálculos gerais excluem também essa marca, além do campo tax_override legado. Alíquota individual acompanha correções posteriores de receita, enquanto valor direto fica fixo. O vínculo original com a regra fica preservado para auditoria, sem participação em recálculos gerais. PostgreSQL já protege tax_amount/tax_snapshot por SaleCorrection; não é necessário alterar schema ou relaxar triggers. Relatórios usam o imposto aplicado na data da venda. Itens, CMV, estoque e caixa não mudam por correção exclusiva do imposto.

Validação cobre valores, alíquota, zero, reenvio, regra geral, correção posterior da base, DRE e navegador. A política complementa ADRs 0009 e 0034.
