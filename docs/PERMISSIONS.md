# Permissões — política vigente desde 18/09/2026

O master (superusuário ativo) administra `/usuarios/`: selecione uma conta, marque autorizações e salve. Desmarcar nega acesso mesmo se um grupo conceder. Revisão otimista evita sobrescrever edição de outra sessão; alteração tem auditoria. Contas master são protegidas; criação de usuário e promoção continuam no admin restrito ao master. Cada funcionário usa login próprio mesmo dentro da rede local.

| Área | Controles independentes |
|---|---|
| Informação comercial | Faturamento consolidado (`view_dashboard`), vendas individuais (`view_sales`), relatório detalhado (`view_sales_report`) |
| Informação sensível | Custos/CMV (`view_costs`), margens (`view_margins`), DRE/resultado acumulado (`view_dre`), saldos/caixa (`view_finance`) |
| Vendas | Rascunhos (`operate_sales`), confirmar, cancelar |
| Estoque | Consultar quantidades, operar, gerir produtos/kits, remover/inativar, gerir locais/marcas/categorias, receber/abrir, ajustar quantidade, transferir, fracionar, corrigir custo, estornar |
| Compras | Operar compras, gerir fornecedor, confirmar, receber, cancelar, relatórios de compras/fornecedor |
| Financeiro | Operar, gerir contas, criar títulos, alterar previsão, pagar, receber, transferir, estornar, cancelar títulos |
| Despesas | Operar, reclassificar, cancelar, recorrência, plano/regras, relatórios |
| Configurações | Empresa, canais, tributos, recálculo retroativo, alertas |
| Auditoria | Consulta de log (sensível: pode revelar valores anteriores e novos) |
| Arquivos | Exportar indicadores, vendas, estoque, compras, financeiro, despesas e DRE, separadamente |

Catálogo executável com códigos e heranças: `apps/accounts/permissions.py`; permissões base em `Company.Meta.permissions`. Operações específicas exigem também `operate_<módulo>`; entradas/correções/estornos de estoque continuam exigindo custo quando necessário. Cadastro de conta exige operação e leitura financeira. Pagar não concede receber, nem transferir, quando a política individual é editada.

**Perfil funcionário com faturamento:** permitir apenas leitura comercial necessária e `view_dashboard`; não marcar custo, margem, DRE, bancos, relatórios de despesas/compras ou auditoria ampla. Exportação e detalhe de vendas são decisões separadas. Para lançar vendas, liberar operar/consultar e confirmar se desejado; cancelamento pode ficar só com gestão.

Não há garantia contra dedução matemática: faturamento + custos + todas as deduções permitem calcular margem. DRE necessariamente revela lucro/custos; auditoria ampla também pode revelar dados sensíveis. Operar compras/financeiro/despesas envolve valores individuais necessários ao trabalho, embora não autorize saldos globais. Não conceder essas combinações a quem deve ver somente faturamento.

Política aplicada no backend, serviços, URLs/API, HTML e arquivos. Notificações de margem exigem `view_margins`; estoque exige `view_stock`; configuração de alertas exige `manage_alerts`. API de resultado individual exige margem e omite CMV sem custo.

## Atualização de instalações existentes

Migration preserva acesso gerencial antigo: detentores de `view_dashboard` recebem relatório detalhado, e detentores de `view_costs` recebem margem. Isso é compatibilidade, não recomendação de perfil para novos funcionários. Revisar concessões com o master antes de operar. Exports não são concedidos automaticamente a grupos existentes. Capacidades de operação herdam regras anteriores até edição individual explícita. Novo backend exige novo login das sessões anteriores.

Revogação vale na próxima requisição; requisição já em andamento e arquivos anteriormente baixados não podem ser recolhidos. Usuário desativado perde sessão válida de acesso na próxima consulta. A conta do serviço de uma futura integração não deve ser master.

Escopo atual é funcional por usuário: não há limitação por carteira de clientes, canal, conta bancária específica ou depósito específico, nem autorização em dupla para pagamentos. Quem recebe leitura de um módulo pode consultar seu conjunto autorizado de dados da empresa. Essas restrições por registro exigiriam outra camada de autorização; não presumir que filtros de tela são controles de segurança.

## Histórico de implementação até a Fase 8 (substituído pela política acima)

Os parágrafos abaixo descrevem concessões anteriores; não usar como matriz atual.
Implementado com User, Group e Permission nativos do Django. Serviços e views verificam permissões, não nomes de grupos. Operacional não ganha indicadores pelo direito de lançar.

| Perfil | Permissões iniciais |
|---|---|
| ADMINISTRADOR | Configuração, indicadores, DRE, custos, financeiro, lançar vendas/estoque/financeiro, consultar auditoria |
| GERENCIAL | Indicadores, DRE, custos |
| FINANCEIRO | Ver financeiro e operar pagamentos/recebimentos |
| VENDAS_OPERACIONAL | Operar vendas |
| ESTOQUE | Operar estoque |

Estoque, vendas, compras, financeiro, despesas e relatórios gerenciais implementados.

Fase 7: `view_dashboard` autoriza consolidados e tabela gerencial de vendas, incluindo CMV/margem por linha; `view_dre` autoriza DRE HTML/API; `view_finance` autoriza lista de compras a pagar e caixa. Dentro do dashboard, resultado por competência exige adicionalmente view_dre, estoque exige view_costs e bancos exigem view_finance. API de indicadores omite esses blocos independentes. Atalhos de operação continuam exigindo as permissões de origem. Lançar vendas/financeiro não autoriza relatórios.

Fase 6: `operate_expenses` permite registros, classificação/cancelamento e recorrência, sem bancos ou consolidados. `manage_expense_rules` gerencia plano e regras. `view_expense_reports` permite consulta e relatório/API por competência, sem escritas. ADMINISTRADOR/FINANCEIRO recebem as três; GERENCIAL recebe relatórios. Migration concede apenas as permissões novas aos perfis existentes. Operacional de vendas não recebe acesso.

Fase 5: `operate_finance` permite títulos, liquidações, transferências e estornos, sem saldos consolidados. `view_finance` permite contas, fluxo diário e API; não permite escritas. Criar/editar/excluir contas exige ambas. Perfis existentes são preservados. Integração automática de títulos não concede acesso financeiro a compradores/vendedores.
Administração de usuários/grupos exige superusuário ativo. O grupo ADMINISTRADOR não equivale a is_superuser. is_staff permite entrar no admin, mas não concede autorização para promover usuários.
Perfis podem ser personalizados no admin. setup_mvet só atribui permissões quando cria um grupo, preservando ajustes posteriores. Nenhum usuário/senha padrão é criado.
Custos e saldos não aparecem no início comum. URLs de indicadores, DRE e financeiro e /api/v1/indicadores validam autorização mesmo quando acessadas diretamente.
Auditoria registra alterações de configuração, identidades/permissões realizadas pelo admin, login/logout e troca de senha sem salvar credenciais nos logs.
Mudanças por shell/SQL não passam pelo fluxo auditado: são procedimentos administrativos excepcionais, não rotina operacional.

## Estoque (Fase 2)
- operate_stock: cadastro, composição, locais, histórico, saída, redução, transferência e fracionamento.
- operate_stock + view_costs: abertura, entrada, acréscimo, correção de custo, carga inicial e estorno.
- operate_sales: consulta de produtos/quantidades e busca, sem edição e sem custos.
- view_costs: consulta do catálogo, custos e valorização, sem permissão automática de escrita.
- API GET /api/v1/produtos/ retorna cost somente com view_costs. Omissão é aplicada no backend.
- Remoção de produto sem uso é permitida; com saldo, composição ou histórico, somente inativação.
- Marcas, categorias e locais são editáveis/inativáveis; não há exclusão destrutiva desses cadastros pela interface.

Fase 3: `operate_sales` permite rascunhos, confirmação e cancelamento integral auditado; não concede `operate_stock` ou `view_costs`. `view_costs` permite leitura de resultado individual em tela/API sem escrita. `manage_configuration` gerencia canais e regras tributárias. Valores lançados são visíveis ao operacional para conferência; custos, CMV, margem e agregados não são exibidos. Listagem de vendas não contém somatórios financeiros.

`manage_configuration` também configura estoque padrão e cria vigências tributárias com recálculo retroativo auditado. `operate_stock` cadastra estoques adicionais; `operate_sales` seleciona estoque e lança taxas extras, sem gerenciar alíquotas.

Fase 4: `operate_purchases` permite fornecedores, compras, parcelas, recebimento e cancelamento; valores da compra são necessários à operação, mas não autoriza custo médio/margem global. `view_purchase_reports` permite consolidados de fornecedor e API de resumo. ADMINISTRADOR/FINANCEIRO recebem ambas; GERENCIAL recebe relatórios. Migration aplica apenas novas concessões aos perfis existentes. `operate_stock` continua necessário para transferir entre depósitos. Vendedor não recebe permissões de compras.

## Notificações
Qualquer usuário autenticado abre a central, mas recebe somente categorias autorizadas. Estoque: operate_stock/operate_sales/view_costs; margem: view_costs; vencimentos: operate_finance/view_finance; backup/configuração/processamento manual: manage_configuration. Preferências e leitura pertencem ao usuário atual. HTML, API, contagens e POST aplicam o mesmo escopo; revogação de permissão oculta avisos já existentes. Ver NOTIFICATIONS.md.

## Bling — capacidades individuais

Consulta da fila (`review_bling`), busca externa (`fetch_bling`), vínculos de produtos (`map_bling_products`) e aprovação/ignorar/reabrir (`approve_bling`) são independentes, sem concessão automática a grupos existentes. Aprovação também exige operar e confirmar vendas. Busca de produto exige consultar estoque. Apenas master ativo autoriza/desconecta OAuth. A fila não exibe custo, CMV, margem ou saldos. Ver BLING_SETUP.md.

Master (superusuário ativo) também pode salvar rascunhos de venda incompletos, definir imposto manual zero sem motivo digitado e ajustar receita com auditoria. A exceção não permite confirmar estoque inexistente ou sobrescrever snapshots. Usuários operacionais não podem atribuir ajustes de receita via POST/serviço. NF opcional não depende de ser master. Ver ADR 0016.
