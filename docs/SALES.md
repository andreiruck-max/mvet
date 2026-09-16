# Vendas — Fase 3
Implementação: `apps/sales`. Validação remota da entrega registrada no PR da fase.

## Uso
1. Em Vendas, administrador cadastra canais e regras tributárias (alíquota, base e vigência). Nenhuma alíquota é presumida.
2. Nova venda: data comercial, NF/série, canal, local e valores totais. Campos financeiros podem ser zero.
3. Buscar SKU/nome, selecionar produto e informar quantidade; adicionar linhas conforme necessário. Busca informa saldo no local selecionado e custo apenas com permissão.
4. Salvar e revisar: rascunho ainda não movimenta estoque. Editar permite corrigir os dados.
5. Confirmar: valida saldo, grava custo e composição, baixa os produtos/componentes e calcula imposto e margem em uma transação.
6. Cancelar: motivo obrigatório; devolve quantidades e valores efetivamente consumidos. Venda e movimentos permanecem no histórico.

## Datas e custo
Data comercial entre o corte e hoje. Baixa física na data atual da confirmação; custo médio atual, explicitamente informado na tela. Não existe reconstrução retroativa de custo. A DRE futura utilizará a data comercial e somente vendas confirmadas. Ver ADR 0008.
CMV por item é soma dos valores reais baixados; custo unitário snapshot é CMV/quantidade (6 casas). O último consumo absorve resíduo de valorização. Kits não têm estoque próprio; composição efetivamente consumida é vinculada por SaleConsumption a StockMovement.

## Cancelamento
Permitido ao usuário com `operate_sales`, sem depender de `operate_stock` ou `view_costs`. Repõe componentes originais mesmo se o kit mudar ou ficar inativo. Valor devolvido é histórico; média atual é recalculada sobre saldo atual mais devolução. Não restaura média antiga sobre compras posteriores.
Cancelamento integral é idempotente. Rascunho cancelado não movimenta. Não há exclusão de venda, edição após confirmação, estorno genérico de operação vinculada a venda ou reabertura de cancelada.
Não há recebíveis/liquidações nesta fase. A Fase 5 deve adicionar bloqueio/tratamento explícito de vínculos financeiros antes de habilitar pagamentos dessas vendas. Devolução parcial é evolução futura.

## Resultado individual
Receita = produtos − desconto + frete recebido.
Contribuição = receita − CMV − frete pago − taxas − imposto − DIFAL − comissão − outros custos variáveis.
Percentual = contribuição/receita × 100; indefinido para receita zero. Contribuição negativa: MARGEM NEGATIVA. Abaixo do limite da empresa: ALERTA. Limite salvo na confirmação. Não é EBITDA.

## Tributos
Selecionar explicitamente regra válida na data comercial, ou valor manual com motivo (inclusive zero). Base: receita operacional ou produtos menos desconto. Imposto arredondado em centavos, HALF_UP. Snapshot conserva nome, ID, alíquota, base, valor e override/motivo. Alteração futura da regra não muda vendas confirmadas. Regras e canais podem ser editados/inativados, sem exclusão pela interface.

## Integridade e permissões
Mutex PostgreSQL compartilhado com estoque/cadastros; locks de produto em ordem de ID; tudo atômico. Confirmação/cancelamento repetidos não duplicam movimentos. UUID identifica criação e rejeita payload divergente. Revisão protege rascunho contra edição perdida/confirmar versão obsoleta.
NF/série têm constraint única, incluindo canceladas. Espaços externos são removidos; letras normalizadas; valores inteiramente numéricos perdem zeros à esquerda. Séries distintas são aceitas.
PostgreSQL bloqueia alteração/exclusão de consumos e snapshots históricos via triggers. Não há editor transacional no admin. Auditoria cobre rascunho com itens, confirmação, cancelamento, canais e impostos.
`operate_sales`: lançar, editar rascunho, confirmar, cancelar, consultar valores informados. Não exibe CMV, custo, margem ou agregados. `view_costs`: consulta de custo/margem individual; não concede lançamento. `manage_configuration`: canais/impostos. API de resultado exige `view_costs` (403 sem permissão). Relatórios consolidados seguem para Fase 7 com permissão própria.
Listagem paginada em 30, pesquisa NF/SKU/nome, canal/status/datas/períodos e ordenação. Sem somatórios financeiros para perfil operacional.
