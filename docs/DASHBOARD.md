## Navegação, compras e canais — 09/10/2026
Submenus por domínio dão acesso direto às parcelas, importações, cadastros e relatórios, respeitando permissões. Estado de expansão é lembrado neste navegador; grupo da página atual abre automaticamente. Dashboard inclui imposto aplicado às vendas confirmadas no período/canal, condicionado a view_margins.
Relatório de vendas substitui o nome Vendas em tabela. Ordem padrão por data crescente, seguida de número de NF numérico crescente dentro do canal. Cartões de canais ativos incluem cadastros sem vendas e filtram mantendo período e demais critérios. Total da empresa limpa o canal e preserva histórico de canais inativos; estes continuam disponíveis no filtro e na listagem histórica. Cadastro/inativação usa manage_channels.
Compras tem abas Notas de compra (uma linha por documento) e Parcelas a pagar (uma linha por obrigação). Resumos abertos usam tabelas com total, quantidade de títulos ainda abertos e média do saldo restante por título aberto; fornecedor ordenado por saldo decrescente. Totais incluem todas as páginas do filtro. Produtos da parcela ficam recolhidos para compactar a lista.

# Dashboard e consultas — direção aprovada em 17/09/2026
## Revisão de vendas e DRE — 08/10/2026
Vendas mantêm 50 registros por página e totais de todas as páginas. Produtos e quantidades aparecem na mesma linha da nota. A coluna Composição foi substituída por imposto sempre visível e deduções/ajustes exibidos quando ao menos uma venda do filtro completo os utiliza. Cabeçalho, células e totais compartilham a mesma definição de colunas. Canais são recolhíveis; o quadro possui rolagem própria com cabeçalho e total fixos, também no celular, sem transbordar a página. Bordas e valores negativos são destacados.

Na DRE, somente master acessa o detalhamento das linhas e categorias históricas, com competência, origem, descrição, valor e navegação até o documento. A soma corresponde à linha selecionada; datas e canal são preservados. Despesas comuns continuam sem rateio por canal. Nova despesa pode trazer a categoria selecionada, quando ainda disponível. Correções usam as ações auditadas existentes nas origens; a consulta não altera lançamentos. Ver ADR 0030.

Atualização 18/09: faturamento, relatório de vendas, custos, margens, DRE e bancos agora têm controles independentes. Exportações Excel/PDF estão nos módulos; ver [PERMISSIONS.md](PERMISSIONS.md) e [EXPORTS.md](EXPORTS.md). Essas regras substituem as permissões agregadas descritas no histórico abaixo.
Estado: Fase 7 implementada e validada em PostgreSQL/Chromium no PR #16. O usuário pediu visualização próxima das planilhas, mantendo as fontes transacionais normalizadas.

## Vendas como planilha
Uma venda por linha, ordenação/paginação e filtros comuns por período, canal, NF e situação. Colunas gerenciais: data, NF/série, canal, estoque, valor dos produtos, desconto, frete recebido, receita operacional, frete pago, CMV histórico, taxas, taxas extras (inclui MDR), impostos, DIFAL, comissão, outros custos variáveis, contribuição em reais e percentual. Abrir NF mostra itens e histórico. Totais representam todo o filtro, não somente a página. Rascunhos/canceladas são claramente distinguidos e excluídos dos resultados confirmados.

Usar nomes gerenciais corretos: resultado de venda é margem de contribuição, não EBITDA. Cópia visual da planilha não autoriza reutilizar denominações incorretas nem recalcular CMV pelo custo atual.

## Caixa por dia
Organizar o período selecionado por data crescente, com um quadro de cada dia e contas dentro do quadro. Mostrar saldo inicial, créditos, débitos, saldo final realizado e projetado. Permitir navegar entre dias, selecionar conta e abrir lançamentos. Na tela ampla, preservar leitura horizontal de dias quando útil, com rolagem própria; no celular, empilhar sem transbordar a página. Dias sem movimento também preservam a continuidade do saldo.

O módulo agrupa contas dentro de dias consecutivos. Períodos de até 366 dias, em páginas de 14 dias, com rolagem horizontal no desktop e empilhamento no celular. Cada página recalcula saldo inicial com todo o histórico anterior; não reinicia saldo em zero. Realizado e projetado não se misturam. Transferências têm efeito zero no consolidado. Pendências sem conta definida até o último dia da página permanecem explícitas.

## Compras a pagar
Lista de parcelas com fornecedor, documento da compra, número da parcela, data da compra, vencimento, principal, pago, pendente, situação e conta prevista. Filtros de período de vencimento e de compra são distintos. Atalho para abrir compra e marcar parcela como paga. Valor total de uma compra aparece uma vez na visão de compras; relatório de parcelas soma obrigações, sem multiplicar total comprado.

## Dashboard
Período global com hoje/ontem/últimos 7 dias/semana/mês/mês anterior/ano/personalizado e canal quando pertinente. Resumo com acesso às tabelas detalhadas e mesmos filtros. Prioridade às tabelas, quadros diários e listas operacionais, além dos indicadores. DRE permanece relatório de competência próprio; despesas comuns não são rateadas por canal silenciosamente.

Rotas: `/indicadores/`, `/relatorios/vendas/`, `/relatorios/compras-a-pagar/`, `/financeiro/`, `/dre/`. Tabelas de vendas/parcelas têm 30 linhas por página; totais abrangem todo o filtro. Períodos rápidos usam o intervalo completo (inclusive datas futuras do mês/ano). Valores de estoque e saldo hoje são posições atuais identificadas, não reconstruções históricas; previsão em 30 dias também tem horizonte próprio. O filtro de canal afeta vendas/contribuição, não bancos, estoque ou despesas comuns. Consulta por NF aparece na tabela de vendas. Rascunhos/canceladas nunca entram nos totais confirmados. CMV mantém seis casas internamente e na tabela; valores gerenciais exibidos em centavos são arredondados somente na apresentação.

Dashboard mostra resultado de competência somente com `view_dre`, estoque com `view_costs` e bloco financeiro com `view_finance`. API de indicadores retorna somente vendas/comparativo, sem banco ou estoque. Relatórios rodam sob a transação/mutex de domínio para evitar misturar partes de operações concorrentes. Não criam saldos, snapshots ou tabelas por mês.

## Permissões e aceite
Operacional não acessa totais, CMV, margens, DRE ou bancos apenas porque lança dados. Proteger as colunas e consultas no backend. Consolidado de vendas exige permissão de indicadores; bancos exigem consulta financeira; DRE exige sua permissão. Testar reconciliação dos totais com snapshots, filtros entre telas, paginação, dias sem movimentos, parcelas parcialmente pagas e bloqueio de URLs/API. Documentar limitações de intervalos grandes sem cortar dias silenciosamente.

## Relatório de vendas compacto — 28/09/2026
Vendas agrupadas por canal, 50 por página, composição detalhada expansível e apresentação móvel sem rolagem horizontal. Cartões do topo mostram confirmadas de todos os canais no período; canal/NF/situação filtram a listagem, não os cartões. Subtotais de canal consideram todas as páginas do filtro. Rascunhos/canceladas fora dos totais. Custos/margens seguem permissões; exportações completas preservadas (ADR 0023).


## Revisão de navegação e densidade — 05/10/2026
A raiz redireciona usuários com view_dashboard para Indicadores; demais usuários mantêm início operacional, sem ganhar permissões. Período padrão é mês atual completo; datas calculadas aparecem nos campos. Editar datas troca o período para Personalizado.

Menu organizado em visão geral, operação, financeiro/resultados e configuração. Conexão Bling fica em configuração. Área principal aproveita a largura disponível; filtros GET, cabeçalhos, tabelas, botões e espaçamentos adotam densidade compacta em todos os módulos. Menu móvel recolhido, expansível por botão acessível.

Dashboard: receita e contribuição por filtro; resultado da empresa e despesas por competência de todos os canais; compras confirmadas/recebidas pela data da compra (uma soma por compra), condicionadas a view_purchase_reports. Saldo bancário atual e projeção em 30 dias exigem view_finance; estoque exige view_costs. Resultado exige view_dre. Projeção consolidada inclui obrigações sem conta definida, como a tela financeira. Resultado é antes de depreciação/amortização e sinaliza pendências de classificação; não é lucro líquido contábil.

Caixa substitui cartões por matriz: contas nas linhas, datas nas colunas, entradas/saídas/saldo, rodapé total. Escolha Somente realizado ou Realizado + previsto. Movimentos previstos são separados por direção antes da soma, evitando ocultar entrada e saída simultâneas. Saldo mantém todas as fontes e continuidade entre páginas; células antes da abertura ficam vazias. Cabeçalho e banco fixos, rolagem própria e linhas alternadas. Cartões usam período inteiro; tabela usa 14 dias por página. Compromissos sem conta ficam fora das linhas por banco e explícitos no aviso. Nenhuma mudança em lançamentos, snapshots ou migrations.
# Vendas em tabela — filtros automáticos (09/10/2026)

Selecionar período, canal, situação ou ordenação aplica a consulta automaticamente. Alterar data seleciona período personalizado; NF é consultada após uma breve pausa na digitação. Consultar permanece como alternativa acessível/sem JavaScript. A consulta reinicia na primeira página. Datas seguem a escolha recentes/antigas, e NFs numéricas ficam crescentes dentro da mesma data e canal; exportação segue o desempate numérico. Não altera dados ou totais.

## 10/10/2026 — cartões e exportações
Total da empresa/estoque primeiro; canais/depósitos em ordem decrescente de valor. Ocultar valores dos cartões persiste no navegador e não substitui permissões; tabelas e arquivos permanecem com os valores autorizados. Exportações de vendas incluem todos os canais por padrão, conservando período/NF/situação. Excel com aba completa, resumo e abas por canal; PDF com resumo e seções que mantêm produtos, deduções e resultado junto à respectiva NF. Depreciação registrada é deduzida após o EBITDA na DRE e no resultado da dashboard.
