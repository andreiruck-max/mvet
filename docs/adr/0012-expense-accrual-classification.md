# ADR 0012 — Despesa e obrigação separadas, classificação histórica
Data: 17/09/2026. Estado: aceito.

## Contexto
O financeiro já distingue obrigação e liquidação. Usar débito bancário como despesa perderia competências futuras, pagamentos parciais e despesas ainda não pagas. Regras de classificação mutáveis não podem reescrever relatórios sem ação explícita.

## Decisão
Expense possui competência e relação única com FinancialTitle. Criação é atômica, sem caixa. Pagamento usa os mesmos serviços financeiros. Natureza/caminho da categoria e regra são snapshots. Correção exige motivo, revisão otimista e registro anterior/novo imutável; pode alterar relatório histórico por ação auditada. Valor/data exigem cancelamento e relançamento. Categoria utilizada conserva estrutura, admitindo renomeação/inativação.

Recorrência é mensal, explícita e pré-visualizada: índice único por base/mês, datas ancoradas no original, hash de prévia e geração atômica sob mutex. Não há execução em segundo plano nesta fase. Cada ocorrência reconhece seu próprio valor uma vez.

## Consequências
Há pendências a classificar visíveis. Plano de contas precisa ser cadastrado pela empresa. Relatórios usam snapshots; renomeações não alteram passado. Reclassificação é uma correção histórica autorizada, sem tocar banco. Juros de liquidação são fonte financeira separada para a política da DRE futura. Sem rateio arbitrário por canal, depreciação ou competência derivada automaticamente do pagamento.
