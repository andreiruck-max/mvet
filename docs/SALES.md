# Vendas — Fase 3
Implementação: `apps/sales`. Entrega e evidências de validação no [PR #12](https://github.com/andreiruck-max/mvet/pull/12).

## Uso
1. Em Vendas, administrador cadastra canais e regras tributárias (alíquota, base e vigência). Nenhuma alíquota é presumida.
2. Nova venda: data comercial, NF/série, canal, estoque e valores totais. O estoque físico padrão é sugerido; pode ser trocado para Full ou outro cadastro. Valores opcionais podem ser zero. Em Configurações, escolha o estoque padrão; em Produtos e estoque → Locais, adicione quantos estoques precisar.
3. Buscar SKU/nome, selecionar produto e informar quantidade; adicionar linhas conforme necessário. Busca informa saldo no local selecionado e custo apenas com permissão.
4. Salvar e revisar: rascunho ainda não movimenta estoque. Editar permite corrigir os dados.
5. Confirmar: valida saldo, grava custo e composição, baixa os produtos/componentes e calcula imposto e margem em uma transação.
6. Taxas extras: adicionar linhas com descrição e valor em reais, como MDR ou antecipação. Somadas aos custos da venda; evitar duplicação no campo Taxas.
7. Cancelar: motivo obrigatório; devolve quantidades e valores efetivamente consumidos. Venda e movimentos permanecem no histórico.

## Datas e custo
Data comercial entre o corte e hoje. Baixa física na data atual da confirmação; custo médio atual, explicitamente informado na tela. Não existe reconstrução retroativa de custo. A DRE futura utilizará a data comercial e somente vendas confirmadas. Ver ADR 0008.
CMV por item é soma dos valores reais baixados; custo unitário snapshot é CMV/quantidade (6 casas). O último consumo absorve resíduo de valorização. Kits não têm estoque próprio; composição efetivamente consumida é vinculada por SaleConsumption a StockMovement.

## Cancelamento
Permitido ao usuário com `operate_sales`, sem depender de `operate_stock` ou `view_costs`. Repõe componentes originais mesmo se o kit mudar ou ficar inativo. Valor devolvido é histórico; média atual é recalculada sobre saldo atual mais devolução. Não restaura média antiga sobre compras posteriores.
Cancelamento integral é idempotente. Rascunho cancelado não movimenta. Não há exclusão de venda, edição após confirmação, estorno genérico de operação vinculada a venda ou reabertura de cancelada.
Não há recebíveis/liquidações nesta fase. A Fase 5 deve adicionar bloqueio/tratamento explícito de vínculos financeiros antes de habilitar pagamentos dessas vendas. Devolução parcial é evolução futura.

## Resultado individual
Receita = produtos − desconto + frete recebido.
Contribuição = receita − CMV − frete pago − taxas − imposto − DIFAL − comissão − outros custos variáveis − taxas extras.
Percentual = contribuição/receita × 100; indefinido para receita zero. Contribuição negativa: MARGEM NEGATIVA. Abaixo do limite da empresa: ALERTA. Limite salvo na confirmação. Não é EBITDA.

## Tributos
Selecionar explicitamente regra válida na data comercial, ou valor manual com motivo (inclusive zero). Base: receita operacional ou produtos menos desconto. Imposto arredondado em centavos, HALF_UP. Snapshot conserva nome, ID, alíquota, base, valor e override/motivo. Regras e canais podem ser editados/inativados, sem exclusão pela interface.

### Edição de alíquota e recálculo autorizado
Em Regras tributárias → Alíquota e vigência, informe nova alíquota, base, data de início e motivo. A vigência inicial da regra permanece preservada.
- Data anterior a hoje: recalcular vendas confirmadas da regra desde a data escolhida até a próxima vigência já cadastrada. Inclui vendas já lançadas dentro desse período, inclusive hoje.
- Hoje ou futuro: preservar vendas já confirmadas. Próximas confirmações usam a alíquota aplicável à data comercial.
- Impostos manuais e vendas canceladas ficam preservados; rascunhos serão calculados ao confirmar.
- Cada recálculo aparece no detalhe da venda, com valor anterior/novo, vigência, usuário e motivo. CMV e estoque não mudam. Margem reflete o novo imposto.
- Alterações sucessivas de mesma data preservam histórico; prevalece a mais recente para novos cálculos.
Ver ADR 0009, que substitui a regra anterior de imutabilidade absoluta do imposto.

## Integridade e permissões
Mutex PostgreSQL compartilhado com estoque/cadastros; locks de produto em ordem de ID; tudo atômico. Confirmação/cancelamento repetidos não duplicam movimentos. UUID identifica criação e rejeita payload divergente. Revisão protege rascunho contra edição perdida/confirmar versão obsoleta.
NF/série têm constraint única, incluindo canceladas. Espaços externos são removidos; letras normalizadas; valores inteiramente numéricos perdem zeros à esquerda. Séries distintas são aceitas.
PostgreSQL bloqueia alteração/exclusão de consumos e snapshots históricos via triggers, com exceção explícita para recálculo tributário vinculado a SaleTaxRevision imutável. Não há editor transacional no admin. Auditoria cobre rascunho com itens, confirmação, cancelamento, canais e impostos.
`operate_sales`: lançar, editar rascunho, confirmar, cancelar, consultar valores informados. Não exibe CMV, custo, margem ou agregados. `view_costs`: consulta de custo/margem individual; não concede lançamento. `manage_configuration`: canais/impostos. API de resultado exige `view_costs` (403 sem permissão). Relatórios consolidados seguem para Fase 7 com permissão própria.
Listagem paginada em 30, pesquisa NF/SKU/nome, canal/estoque/status/datas/períodos e ordenação. Sem somatórios financeiros para perfil operacional.

## Atualização — vendas sem NF e master (ADR 0016)

Nova venda é independente do Bling. NF opcional; várias vendas sem NF recebem referência interna distinta. Unicidade por NF/série permanece para documentos preenchidos.

Master salva rascunhos sem preencher campos comerciais. Data vazia usa hoje; valores vazios usam zero; sem regra tributária ou imposto informado registra override zero auditado. Produto selecionado com quantidade vazia usa 1. Canal, estoque e itens podem ficar pendentes apenas em rascunho; confirmação exige contexto completo, quantidade positiva e saldo. Outros usuários mantêm validações usuais.

Campo do master Receita líquida operacional ajustada determina um ajuste separado, antes de CMV, impostos e demais custos. Valor é usado também no recebível, indicadores, DRE e Excel/PDF; não é o repasse líquido do marketplace. Motivos de imposto/ajuste podem ser omitidos pelo master, recebendo texto padrão na auditoria. Corrigir venda já confirmada continua exigindo fluxo rastreável, sem sobrescrever snapshots.

## MVet 1.5
Confirmação consome quantidade e custo médio do depósito gravado na venda, inclusive componentes de kits. Canal Mercado Livre não identifica por si só Loja ou Full: conferir o depósito antes de confirmar. CMV já confirmado permanece imutável. Cancelamento devolve ao mesmo local pelo valor original.
