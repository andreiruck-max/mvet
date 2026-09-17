# Dashboard e consultas — direção aprovada em 17/09/2026
Estado: critérios da Fase 7, ainda não implementados. O usuário pediu visualização próxima das planilhas, mantendo as fontes transacionais normalizadas.

## Vendas como planilha
Uma venda por linha, ordenação/paginação e filtros comuns por período, canal, NF e situação. Colunas gerenciais: data, NF/série, canal, estoque, valor dos produtos, desconto, frete recebido, receita operacional, frete pago, CMV histórico, taxas, taxas extras (inclui MDR), impostos, DIFAL, comissão, outros custos variáveis, contribuição em reais e percentual. Abrir NF mostra itens e histórico. Totais representam todo o filtro, não somente a página. Rascunhos/canceladas são claramente distinguidos e excluídos dos resultados confirmados.

Usar nomes gerenciais corretos: resultado de venda é margem de contribuição, não EBITDA. Cópia visual da planilha não autoriza reutilizar denominações incorretas nem recalcular CMV pelo custo atual.

## Caixa por dia
Organizar o período selecionado por data crescente, com um quadro de cada dia e contas dentro do quadro. Mostrar saldo inicial, créditos, débitos, saldo final realizado e projetado. Permitir navegar entre dias, selecionar conta e abrir lançamentos. Na tela ampla, preservar leitura horizontal de dias quando útil, com rolagem própria; no celular, empilhar sem transbordar a página. Dias sem movimento também preservam a continuidade do saldo.

O módulo atual já entrega quadros por conta/data e detalhamento; a Fase 7 ajustará agrupamento/apresentação para aproximação da planilha. Realizado e projetado não se misturam. Transferências têm efeito zero no consolidado. Pendências sem conta definida permanecem explícitas.

## Compras a pagar
Lista de parcelas com fornecedor, documento da compra, número da parcela, data da compra, vencimento, principal, pago, pendente, situação e conta prevista. Filtros de período de vencimento e de compra são distintos. Atalho para abrir compra e marcar parcela como paga. Valor total de uma compra aparece uma vez na visão de compras; relatório de parcelas soma obrigações, sem multiplicar total comprado.

## Dashboard
Período global com hoje/ontem/últimos 7 dias/semana/mês/mês anterior/ano/personalizado e canal quando pertinente. Resumo com acesso às tabelas detalhadas e mesmos filtros. Prioridade às tabelas, quadros diários e listas operacionais, além dos indicadores. DRE permanece relatório de competência próprio; despesas comuns não são rateadas por canal silenciosamente.

## Permissões e aceite
Operacional não acessa totais, CMV, margens, DRE ou bancos apenas porque lança dados. Proteger as colunas e consultas no backend. Consolidado de vendas exige permissão de indicadores; bancos exigem consulta financeira; DRE exige sua permissão. Testar reconciliação dos totais com snapshots, filtros entre telas, paginação, dias sem movimentos, parcelas parcialmente pagas e bloqueio de URLs/API. Documentar limitações de intervalos grandes sem cortar dias silenciosamente.
