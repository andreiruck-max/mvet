# 0049 — Evolução por calendário e cenários mensais

Data: 02/11/2026. Status: aceito.

A tela independente /indicadores/evolucao/ exige view_dashboard. CMV, contribuição e resultado seguem respectivamente view_costs, view_margins e view_dre no backend e na interface. Valores não autorizados não entram no contexto. O cartão CMV do dashboard participa da ordem salva por usuário.

A data de corte fica entre o início do histórico da empresa e hoje. Histórico mensal abrange até 12 meses; anual, até 5 anos. Períodos anteriores ao corte da empresa não são inventados. Períodos iniciais parciais são identificados e não servem de base de crescimento. Meses sem vendas dentro do histórico entram como zero. Vendas confirmadas, CMV histórico efetivo e DRE usam os seletores oficiais, com correções atuais; não representam fechamento congelado.

Comparação mensal usa o mesmo dia em todos os meses (limitado ao último dia dos meses menores). Anual usa o mesmo mês e dia, limitando 29/02 a 28/02 em anos comuns. Variação percentual exige base positiva. Variação entre totais completos não compara mês/ano atual parcial contra anterior completo. Médias mostram denominadores; meses iniciais/finais parciais são incluídos sem anualização. Margem e ticket são ponderados pelos totais.

Cenário do mês: receita anterior inteira × receita atual acumulada ÷ receita anterior no mesmo corte. Sem base anterior completa e positiva, usa receita acumulada ÷ dias observados × dias do mês. Sem receita atual positiva ou início do mês anterior ao corte do sistema, não estima. No último dia do mês usa o registrado. Não ajusta dias úteis, sazonalidade ou feriados e não é previsão probabilística.

CMV e deduções projetadas mantêm as proporções atuais da receita; contribuição deriva desses componentes. Resultado estimado = contribuição projetada menos demais componentes líquidos da DRE já lançados para o mês inteiro (inclusive despesas futuras por competência, depreciação, ajustes de custo e financeiro). Despesas ainda não registradas não são previstas. Isso não projeta caixa. Canal filtra vendas e contribuição; não rateia despesas comuns nem mostra resultado da empresa. Nenhuma escrita financeira ou alteração de schema.
