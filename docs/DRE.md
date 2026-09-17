# DRE gerencial — contrato para Fase 7
Estado: especificado; tela atual informa implantação, sem números.

| Linha | Fonte por competência |
|---|---|
| Receita bruta | Valor dos produtos nas vendas confirmadas |
| Descontos | Redução das vendas |
| Frete recebido | Receita adicional |
| Receita operacional | Produtos − descontos + frete recebido |
| CMV | Snapshots históricos dos itens |
| Custos variáveis | Frete pago, taxas, comissão, imposto, DIFAL e outros |
| Margem de contribuição | Receita operacional − CMV − variáveis |
| Despesas operacionais | Despesas por competência e plano |
| EBITDA gerencial | Margem − despesas operacionais antes de depreciação/amortização |
| Depreciação/amortização | Quando implementadas |
| Resultado financeiro | Juros e receitas financeiras |
| Resultado gerencial | EBITDA − depreciação/amortização + resultado financeiro |

Compra de estoque não é despesa imediata. Transferências, aportes, retiradas patrimoniais, abertura e principal de dívida não são operação da DRE. Venda a prazo é competência hoje e caixa na liquidação.
Filtros por período/canal não devem ratear despesas comuns arbitrariamente: exibir despesas não atribuídas separadas ou adotar rateio documentado.
Não apresentar gráfico/KPI antes de reconciliar fontes com movimentos e snapshots.

Fase 6 entrega Expense ativo por competência e natureza histórica (OPERATING, FINANCIAL ou não classificada). Obrigação e pagamento vinculados não duplicam despesa. Correção auditada de classificação altera o relatório da competência original. Não classificados precisam aparecer explicitamente. Juros de liquidação exigem política de reconhecimento e prevenção de dupla contagem na Fase 7. Ver docs/EXPENSES.md.
