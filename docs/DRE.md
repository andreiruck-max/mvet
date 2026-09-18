# DRE gerencial — Fase 7
Estado: relatório HTML/API implementado e validado no PR #16. Política de reconhecimento detalhada no ADR 0013.

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

Fase 6 entrega Expense ativo por competência e natureza histórica (OPERATING, FINANCIAL ou não classificada). Obrigação e pagamento vinculados não duplicam despesa. Correção auditada de classificação altera o relatório da competência original. Não classificados aparecem explicitamente. Juros de liquidação seguem a política de reconhecimento abaixo. Ver docs/EXPENSES.md.

## Política implementada
- Vendas confirmadas por data comercial; cancelamento integral exclui a venda, sem recalcular CMV. Vigência tributária retroativa autorizada reflete os valores auditados vigentes.
- Expense ativo por competência e natureza histórica; pagamento do título associado não repete despesa. Reclassificações explícitas alteram o histórico gerencial com revisão.
- Título **manual**, financeiro, não legado e sem vínculo de despesa/compra/venda: reconhece integralmente na data de origem, tratada como competência. Pagamento ou parcelamento não altera esse reconhecimento. Para juros ainda não incorridos, informe a data de competência efetiva, não a contratação do empréstimo. Principal patrimonial nunca entra.
- Acréscimo/juros do campo de liquidação representa valor adicional apurado naquela data, fora do principal já reconhecido. Estorno inverte esse adicional na data efetiva do estorno. Não registrar o mesmo valor também como despesa ou outro título financeiro.
- Descontos/abatimentos de liquidação podem ser retenção de taxas já lançadas na venda; não são classificados automaticamente como resultado financeiro. O volume de abatimentos e seus estornos no período aparece como pendência, sem compensação silenciosa. Sem correção/classificação do evento, resultado permanece parcial.
- Títulos manuais operacionais/a classificar não têm competência validada no módulo Expense; aparecem como pendência. Não são somados automaticamente como despesa nem inferidos do débito bancário.
- Não classificados e pendências tornam o resultado **PARCIAL**. Depreciação/amortização ainda não são registradas; último subtotal se chama **Resultado gerencial antes de depreciação/amortização**.
- Filtro por canal calcula apenas sua contribuição; despesas da empresa são mostradas separadas. EBITDA e resultado gerencial por canal não são calculados sem política de rateio.

O relatório consulta a situação atual dos registros, não uma versão congelada no fechamento do mês. Correções/cancelamentos autorizados podem alterar períodos anteriores. Fechamento contábil, razão oficial e ajustes de competência por apropriação diária ainda não fazem parte do ERP gerencial.

A receita inclui ajuste gerencial explícito definido pelo master (ADR 0016): produtos − desconto + frete recebido + ajuste. A DRE e suas exportações mostram o ajuste em linha própria; não é CMV, imposto ou taxa. Rascunhos incompletos e vendas canceladas não integram os totais.
