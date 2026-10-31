Atualização 31/10/2026: PDFs com linhas e títulos compactos, cabeçalhos repetidos e seções que aproveitam a página disponível. Comissões preservam todos os termos e valores, com critérios no final e aviso simples quando não há pagamentos. Títulos acompanham o início da tabela sem empurrar todo o detalhamento para outra página. Vendas por canal, blocos de colunas, estoque por local e grupos de três dias do caixa não abrem páginas obrigatórias. Cada comissionado continua iniciando uma página própria. Sem mudança de cálculos, permissões ou dados do Excel.

Atualização 28/10/2026: CRM preserva filtros e página por sessão, separadamente em Pendências e Contatos. Abrir, editar ou registrar contato mantém a origem no retorno. Limpar remove os filtros da lista atual; resultados são consultados novamente, respeitando a carteira e a próxima ação atualizada.

Atualização 21/10/2026: falha de consulta ao Bling preserva opções de depósito e última comparação. Não exibe seleção inválida quando as opções não puderam ser carregadas. Leituras GET com HTTP 500/502/503/504 têm uma única repetição; escritas nunca são repetidas automaticamente.

Atualização 21/10/2026: conferência Bling ordenada por SKU numérico crescente antes da paginação de 50 produtos, usando a mesma regra do estoque. Consulta salva mantém seus itens e é ordenada sem nova chamada à API.

## Conferência Bling — consulta preservada (21/10/2026)

Busca local por SKU exato, filtro imediato sem nova chamada remota e última página consultada persistida por usuário. Retorno após correção preserva parâmetros e atualiza a linha confirmada. Valores externos normalizados com Decimal (2 casas preço, 4 saldo); saldo inválido bloqueia somente o item.

## Bling — comparação de estoque, preço e cadastro (20/10/2026)

Estoque → Conferir com Bling, exclusivo master: saldo físico por depósitos escolhidos e preço de venda lado a lado, diferenças destacadas, busca e paginação. Correção individual nos dois sentidos com prévia, motivo, releitura e histórico; falha ambígua não é reenviada. Preço fixo opcional preserva valor exato importado; estoque usa movimentos atuais sem reescrever CMV. Catálogo externo permite cadastrar produto com revisão de descrição/preço e estoque opcional mediante custo informado. ADR 0048. Requer novos escopos e reautorização; homologação real ainda depende da instalação do usuário.

Atualização 20/10/2026: Apuração mensal de comissões exporta PDF por vendedor e Excel com abas de resumo, liberações/ajustes e pagamentos do mês. Respeita mês e comissionado; funcionário exporta apenas a própria pessoa vinculada. Usa bases/percentuais históricos dos eventos, saldos até o corte e pagamentos/estornos. Explica a diferença entre pago no mês e pago da apuração; não inclui custos, margens ou bancos.

Atualização 20/10/2026: planejamento inclui Marcar todos desta página, Desmarcar todos e contagem da seleção para exportação. Ações selecionam o modo de exportar itens marcados; todos os filtrados de todas as páginas continuam disponíveis no seletor.

## Planejamento — exportação para cotação (20/10/2026)

PDF e Excel com SKU, produto, unidade e quantidade sugerida, para todos os resultados filtrados ou itens marcados da página. Preserva depósito, prazos, busca e filtro de necessidade; não inclui custos/margens e não cria pedidos. Exige export_purchases além do acesso ao planejamento. Quantidades com quatro casas no PDF e números no Excel.

## Estoque — filtro de necessidade no planejamento (19/10/2026)

Planejar compra abre com “Somente o que precisa comprar”: sugestão maior que zero após saldo e compras a receber. Opção “Todos os produtos” disponível e lembrada na sessão. Filtro aplicado antes da paginação, combinado com depósito/prazos/pesquisa e fora de linha; cartões mantêm o universo analisado. Seleção automática, com botão Calcular preservado.

## Vendas — correção individual do imposto (19/10/2026)

Corrigir venda oferece manter tratamento atual, informar nova alíquota ou informar valor direto do imposto. Master pode aplicar inclusive zero, com motivo e histórico antes/depois; usa SaleCorrection e as proteções PostgreSQL existentes. A alíquota específica utiliza a base histórica (receita incluindo ajuste gerencial ou produtos menos desconto), já considerando as correções da tela. Sem base histórica, usar valor direto. Valor manual fica fixo; alíquota específica acompanha futuras correções da base. Alteração geral da regra não sobrescreve correções individuais. Não altera outras vendas, CMV ou estoque. DRE e relatórios refletem a correção na data original. ADR 0047.

## Compras — pesquisa e grupos de categorias (16/10/2026)

Categoria sem estoque permite pesquisar por código, nome ou grupo, sem diferenciar acentos/maiúsculas. Plano apresentado com títulos de grupos em negrito e subcategorias selecionáveis; níveis intermediários identificados pelo caminho do grupo. Pesquisa preserva a escolha atual, é independente por item e funciona também em linhas adicionadas na compra manual. Conferência Bling e rascunho manual compartilham o seletor. Cálculos e classificação histórica preservados.

## Despesas — edição auditada e baixa em lote (16/10/2026)

Ficha inclui Editar despesa para master, com motivo, revisão e sincronização do título: valor, datas, descrição, categoria, favorecido, fornecedor, centro de custo, observação, recorrência e conta prevista. Histórico mostra antes/depois. Pagamentos preservados; não permite valor abaixo do liquidado nem documento após pagamento. Migração 0006 permite somente edições respaldadas por revisão, mantendo proteções SQL e livro imutável.

Lista permite selecionar pendentes da página e conferir baixa conjunta em uma conta/data. Cada despesa mantém categoria e lançamento; saldo integral sem juros/descontos. Prévia assinada, confirmação atômica, proteção contra conflito e reenvio duplicado. Baixas futuras mantêm efeito na data. ADR 0046.

## Despesas — cartões compactos (16/10/2026)

Totais em uma faixa compacta no computador e duas colunas no celular, com fontes, espaçamentos e explicações reduzidos. Cálculos, filtros e permissões preservados.

## Despesas — cartões e filtros automáticos (16/10/2026)

Lista de despesas mostra total registrado, principal liquidado (incluindo baixas futuras), saldo pendente e saldo vencido sobre todos os registros filtrados, antes da paginação. Canceladas e despesas sem movimento financeiro são destacadas separadamente quando presentes; canceladas não compõem o total registrado. Juros e descontos não são confundidos com o principal. Cartões exigem view_expense_reports, preservando a permissão de consolidados. Seleções/datas aplicam filtros automaticamente; textos após pausa de 700 ms, na lista e no relatório. Botão continua disponível sem JavaScript.

## CRM — atividades detalhadas do funcionário (16/10/2026)

Visão Master inclui lista paginada de atividades por autor e período, do mais recente para o mais antigo, com divisórias por dia. Atalhos Hoje, Ontem, Últimos 7 dias e Este mês; datas personalizadas disponíveis. Cada registro mostra cliente, data/hora, autor, canal/tipo, resultado histórico, próximo contato registrado e mensagens/observação expansíveis. Link abre a ficha completa. Filtros e totais preservados na paginação.

Atividade realizada por filtra o autor histórico, incluindo usuários inativos; Responsável atual da carteira continua separado e opcional. Resultado da atividade filtra o registro histórico, não o último resultado atual do cliente. Contagens são de registros, não de clientes distintos. Pendências/carteiras mostram a posição atual; atividades usam data informada no fuso local. Horário de gravação é exibido nos detalhes para distinguir registros retroativos. Somente master; histórico e operações comerciais não são alterados.

## Estornos de créditos e débitos diretos — 16/10/2026

Estornar Novo crédito/Novo débito cancela também o título auxiliar criado pelo atalho. O valor não reaparece como previsão. Estorno de pagamento/recebimento de obrigação independente continua reabrindo o título. Livro bancário preservado. Migração 0004 corrige títulos auxiliares antigos em todas as contas quando identificados pelo UUID do atalho, totalmente estornados e sem alterações posteriores (revisão 2); títulos reagendados ou reutilizados ficam preservados para conferência. Cada reparo gera auditoria. A visão Realizado + previsto continua incluindo compromissos legítimos; Somente realizado corresponde ao saldo efetivo do extrato.

## Correção auditada do CMV — 15/10/2026

Master: abra a venda confirmada → **Corrigir CMV** → informe custo correto por unidade vendida e motivo → **Conferir correção** → **Confirmar correção do CMV**. Kits usam custo de um kit completo. Prévia mostra custo anterior/novo, CMV total e contribuição. Resultado é corrigido na data da venda em dashboard, DRE, relatórios e exportações. Original e histórico ficam preservados. Não altera o estoque atual, impostos ou financeiro; eventual erro do saldo/custo atual deve ser conciliado separadamente. Cancelamento exclui do resultado; recuperação mantém a correção. ADR 0044.

## Bling — XML opcional (15/10/2026)

Falhas na consulta ou validação do XML não bloqueiam a importação de compras e vendas. Aviso orienta conferir descontos manualmente; não há inferência por diferença de totais. Mantidas validações fiscais, segurança do download e confirmação local.

## Extrato bancário — mês e saldos (15/10/2026)

Ao abrir uma conta, o período padrão é o mês atual, inclusive com parâmetros de navegação. Lançamentos aparecem do mais recente ao mais antigo; saldo acumulado continua calculado cronologicamente. Abertura aparece ao final da última página. Cartões mostram saldo realizado hoje e saldo no último dia do filtro (previsto se futuro, realizado se passado).

## Fluxo de caixa — leitura dos pagamentos (15/10/2026)

Pagamentos pendentes e futuros ficam sempre expostos, sem acordeão. Removido o bloco Como ler os saldos. Vencimentos atrasados e de hoje recebem cor e rótulo textual; divisórias identificam mês e ano. Preservados filtros, paginação e regras financeiras.

## Retorno à fila do Bling
- Série e demais filtros são preservados ao abrir uma nota, vincular produto, registrar venda ou reconsultar o documento e voltar às notas.

## Atalhos de período nas comissões
- Hoje, ontem, últimos 7 dias, esta semana, semana passada, este mês, mês passado e este ano; aplicação automática e datas manuais preservadas.

## Filtro automático de comissões
- Selecionar um comissionado aplica o filtro imediatamente, preservando os demais critérios da consulta.

## Filtro após consulta ao Bling
- Ver notas consultadas e pendências abre somente pendentes nas filas de vendas e compras. Ignoradas continuam acessíveis pelo filtro manual.

## Navegação e leitura compacta
- DRE e estoque com título, filtros e dados mais próximos; ações secundárias recolhíveis.
- Menu em acordeão, ordenação por arraste/setas por usuário neste navegador, restauração da ordem e notificações no sininho superior.

## Posição de estoque por Excel
- Modelo XLSX e importação pela tela, com seleção de depósito, quantidade, custo médio e novos produtos.
- Substituição atual ou posição histórica; ausentes preservados por padrão e prévia antes de aplicar.
- Contagens distintas no mesmo dia, sem duplicar reenvio idêntico; validações e histórico preservados.

## Correção visual e conferência de estoque — 12/10/2026
- Azul-escuro da marca aplicado à navegação, ações, tema escuro e relatórios PDF.
- Prévia da conciliação separa valor do arquivo, saldo anterior e resultado com movimentos posteriores.
- Comando inspect_inventory_base consulta aplicação da base e movimentos posteriores/retroativos sem alterar dados.
- Saldos reais dependem da conferência no computador do usuário; nenhuma carga automática nesta atualização.

## 12/10/2026 — MVet 2.0
- Central de configurações por domínio e gestão nativa de funcionários, senhas e situação.
- Permissões agrupadas, busca, perfis editáveis e alertas de dependências/acessos sensíveis.
- Políticas revisadas negam novas capacidades por padrão; histórico e permissões existentes preservados na instalação.
- Identidade 2.0 em login, menu, início e administração. ADR 0041.

## 12/10/2026 — Interface e relatórios
- Menu pesquisável com localização atual, controles consistentes, foco acessível e leitura comum em temas claro/escuro.
- Matriz de caixa preservada, com total fixo e contraste revisado.
- PDFs com fontes incorporadas, números alinhados, larguras por conteúdo, DRE destacada e notas longas completas; caixa em grupos de três dias. Sem migration.

## 10/10/2026 — Controle de comissões
- Previsão por venda, rateio por parcela, recebimentos parciais, pagamentos alocados e apuração mensal.
- Comissionados, percentuais, consulta própria e gestão autorizada; estornos, correções e compensações com histórico.
- Integração auditada ao custo da venda sem duplicar DRE ou criar recebíveis/bancos. Ver docs/COMMISSIONS.md.

# CRM / Comercial — 10/10/2026
Carteiras por funcionário, contatos simplificados, histórico separado de mensagens, próxima ação automática, regras master, pausas, aprovação de inativação, não contatar imediato, reativação, importação CSV/XLSX com prévia e validação, indicadores operacionais e telas responsivas. Permissão independente; sem integração WhatsApp/IA ou efeitos em estoque/financeiro. Migrações criam tabelas CRM, regras iniciais, proteções do histórico e permissão. ADR 0035; docs/CRM.md.

# Navegação, compras a pagar e relatório de vendas — 09/10/2026
Submenus por domínio; imposto na Dashboard; cartões de canais ativos clicáveis; ordem padrão data/NF crescente. Compras e parcelas com abas, resumos legíveis por mês/fornecedor (saldo, quantidade e média), fornecedores por maior saldo, ação Pagar / antecipar e divergências exatas. Sem migration ou alteração automática dos lançamentos existentes.

# Correção de canal e depósito da venda — 09/10/2026
Master pode usar Corrigir venda para alterar canal e depósito junto aos valores. Troca de depósito registra estorno e nova saída auditados; CMV histórico preservado e diferenças de estoque no resultado da data atual. Migration 0012; ADR 0034. Sem alteração automática de vendas existentes ou instalação local.

# Correção Bling — Emitida DANFE (09/10/2026)
Busca padrão por Autorizada + Emitida DANFE; confirmação e recuperação aceitam status 6. Impressão não gera divergência comercial nem duplicação. ADR 0033. Busca direta vazia na API ainda em diagnóstico; sem instalação local automática.

# Novo pacote — aguardando OK para instalação
- Vendas em tabela: filtros aplicados automaticamente e NF numericamente crescente dentro da data, mantendo datas recentes/antigas.
- Compras: desconto total por item, sem repassar a promoção aos demais produtos; base líquida para rateios gerais e conferência de total/parcelas. ADR 0032.
- Fornecedor pode ser cadastrado junto com o rascunho importado, com dados disponíveis na nota e permissões preservadas.
- Conta bancária: botões Novo crédito e Novo débito com direção previamente selecionada, utilizando o livro financeiro existente.
- Correção auditada dos valores de venda confirmada pelo master, sem nova baixa de estoque; recuperação de canceladas destacada e orientação para NF já cadastrada. ADR 0031.
- Consulta Bling por número/série, inclusive sem loja externa, sem restringir data/situação quando o número é informado.
- Digitação monetária por centavos, cartões de indicadores com links e navegação de conferência no topo.
- Vendas com colunas alinhadas, produtos/quantidades, imposto e deduções visíveis quando utilizadas no filtro completo; totais e cabeçalhos fixos, canais recolhíveis e negativos em vermelho.
- Master pode abrir lançamentos da DRE por linha/categoria histórica e acessar a origem ou iniciar uma despesa extra. Preserva permissões, snapshots e correções auditadas. ADR 0030.
- Calendário ao clicar no campo; notas de venda por série e número crescente, com valor fiscal e nome do cliente sem cadastro adicional.
- Regra tributária vigente na data comercial sugerida e editável.
- Venda permite estoque negativo usando último custo local conhecido. Reposição e estornos conciliam diferenças de custo sem alterar CMV histórico; diferenças aparecem na DRE e indicadores de resultado. ADR 0029.

# Recuperação de venda cancelada por engano (07/10/2026)
- Master pode recuperar venda e corrigir Taxas com histórico imutável, nova saída vinculada ao estorno, preservação de CMV/imposto/data e manutenção do vínculo Bling.
- Resultados passam a considerar a mesma venda confirmada; nenhuma reimportação ou recebível duplicado. Saldo inconsistente, divergência Bling e financeiro histórico bloqueiam integralmente. ADR 0028.

# Correção do atualizador Windows (07/10/2026)
- Verificação de inicialização tolera stderr transitório no PowerShell 5.1, repete a tentativa pelo código de saída e conserva o diagnóstico final. Teste com stderr nativo também executado em Windows.

# Plano de contas e nova despesa (07/10/2026)
- Código sugerido automaticamente por grupo, editável e sem renumerar cadastros existentes.
- Formulário compacto, favorecido livre e opcional, fornecedor cadastrado em seção adicional.
- Pesquisa de categoria por código/nome com caminho hierárquico e exclusão de ancestrais inativos.
- Atualizador Windows com preservação dos scripts locais, backup/restauração isolada antes de migrations e verificação de inicialização. Sem alterações de schema nesta etapa.

# Saldos bancários e fluxo de caixa (07/10/2026)
- Período inicial de 15 dias a partir de ontem; intervalo inteiro na mesma tabela, sem paginação de dias.
- Cabeçalho Banco / conta fixo sem sobreposição com Entradas; bordas de células e separação de dias reforçadas.
- Entradas azuis, saídas/negativos vermelhos e saldos pretos em negrito sobre fundo claro inclusive no modo escuro.
- Conta clicável abre extrato com saldo acumulado, compromissos e ações de lançamento, previsão, transferência e edição.
- Adicionar conta no fluxo; inativas saem do quadro e seus totais sem apagar histórico nem alterar indicadores consolidados. ADR 0027.

# Vínculo de vendas e planejamento de compra (07/10/2026)
- Vínculo por código independente da unidade externa; seleção do item da nota, unidade local e quantidade preservada.
- Confirmação única de venda, sem checkbox adicional de finalidade; aviso, auditoria e bloqueios de documentos incompatíveis mantidos.
- Estoque inicia em Com saldo, com opção de desmarcar e exportação consistente.
- Planejar compra por depósito, histórico/cobertura configuráveis, estoque mínimo, compras a receber e prazo de fora de linha para zerados sem movimento; não altera cadastro nem gera pedidos.
- Sem alteração de schema nesta etapa; pacote permanece separado da instalação local. ADR 0026.

# Bling — seleção em massa e compras flexíveis (06/10/2026)
- Seleção de notas por página ou filtro, com prévia, ignorar/reabrir e modificar preenchimento em lote; revisões assinadas e aplicação atômica. Não confirma vendas/compras em massa.
- Cadastro de produto na importação com SKU, unidade e nome local editável; código externo vazio não bloqueia identificação manual.
- Item somente financeiro sem cadastro de produto, com categoria e parcela de rateio próprias. Total integral a pagar preservado; somente itens estocáveis afetam estoque/custo.
- Bonificação x910 explicitamente selecionada: quantidade recebida a custo zero, sem parcelas; fiscal e CMV histórico preservados.
- Reconhecimento dos itens sem estoque na DRE por categoria histórica, sem duplicar obrigações. Categorias patrimoniais não são despesas da empresa.
- Migrações aditivas; implantação local adiada para o pacote de alterações solicitado pelo usuário. ADR 0025.

# Bling — conferência compacta e vendas sem contas a receber
- Filtros compactos e atalho para relatório de vendas.
- Sugestões configuráveis Full/demais lojas, com alteração manual por nota.
- Frete da nota sugerido nos campos recebido e pago; deduções iniciam em 0,00.
- Imposto manual e caixa genérica de conferência removidos dessa tela; finalidade ausente mantém declaração específica.
- Novas vendas não geram recebíveis; histórico financeiro preservado.

# Correção Bling — UN e UNID
- Reconhecimento de UN/UNID no SKU e vínculo manual; unidades de peso, volume e embalagem continuam distintas. Sem migração de dados.

# MVet 1.5 — contagem e navegação de estoque
- Contagem física por produto/depósito com ajuste da diferença, motivo, auditoria e proteção contra movimentação concorrente e envio duplicado.
- Filtro Com saldo do depósito selecionado, valores com ponto de milhar e botões Voltar com preservação de contexto.
- Inativar e excluir visíveis no produto; histórico e saldos preservados.
- Full inicial padronizado; cadastro legado duplicado removido somente quando sem vínculos.

# MVet 1.5 — estoque e custo por depósito
- Alternância de depósitos, 50 produtos por página, SKU numérico e pesquisa exata de códigos numéricos.
- Totais permanentes por depósito e consolidado, com proteção de custos e exportação do local selecionado.
- Custo médio independente por depósito; vendas, kits, transferências e fracionamento consomem o custo local.
- Migração recupera valores pelo livro sem reescrever movimentos nem CMV histórico; inconsistências bloqueiam a atualização.

# Posição inicial por depósito
- Importador JSON privado com simulação, carga atômica e repetição sem duplicar.
- Um cadastro por SKU, saldos por depósito, custo médio ponderado e data explícita da posição.
- Bloqueia SKUs existentes e saldos negativos; não sobrescreve movimentos nem gera resultado.

# Bling — busca automática do período
- Um clique percorre os lotes com progresso, interrupção e retomada; nenhuma venda é confirmada na busca.
- Pendências documentais não interrompem as demais notas; falhas técnicas param sem pular a página.

# Correção Bling — finalidade ausente
- Notas sem finalidade informada entram na fila com aviso e exigem conferência explícita auditada.
- Bloqueios de finalidade não normal, situação, tipo e CFOP preservados; reconsulta recupera erro anterior sem duplicar.

# Preparação da instalação
- Checagem sem escrita de configuração, PostgreSQL, migrations e cadastros essenciais, com saída JSON.
- Roteiro de implantação e aceite na rede interna, incluindo permissões, exportações e recuperação.

# Vendas manuais e flexibilidade do master
- NF opcional com referência interna; master salva rascunhos incompletos.
- Imposto zero e ajuste de receita auditados; recebível, DRE e exportações consistentes.
- Confirmação mantém validação de estoque, quantidades e contexto; histórico não é sobrescrito.

# Integração assistida Bling — homologação real pendente
- Conexão OAuth pelo master com tokens criptografados e leitura paginada de NF.
- Fila separada, SKU/unidade, deduções explícitas e taxas extras; confirmação atômica pelo CMV do MVet.
- Cancelamentos independentes, snapshots de origem e referência protegida contra duplicação/reativação.
- Permissões individuais, histórico de consultas e comando sync_bling. Financeiro externo ainda não implementado.

# Especificação — integração Bling independente
- Fila de conferência, deduções manuais e CMV exclusivo do MVet definidos no ADR 0015.
- Cancelamentos independentes e reconsultas sem duplicação/reativação; integração ainda não implementada.

# 0.8.0 — Notificações internas
- Central paginada com severidade, links, leitura por usuário e filtros.
- Estoque mínimo, margem e vencimentos com resolução e reativação sem duplicidade.
- Preferências e configuração auditadas; escopo HTML/API reavaliado a cada acesso.
- Comando periódico independente das transações e evidências de backup no script.

# 0.7.0 — Dashboard e consultas gerenciais
- Vendas como planilha, com filtros, colunas de valores/deduções, margem e totais de todo o filtro.
- Caixa por dia com contas dentro de cada quadro, navegação de 14 dias e períodos de até 366 dias.
- Compras a pagar por parcela, vencimento, fornecedor e período de aquisição; principal baixado separado de pagamento efetivo.
- Dashboard com comparativo por canal, DRE e blocos protegidos por permissão.
- DRE usa snapshots e competência, exclui compras/principal/aberturas/transferências e não duplica liquidação.
- Pendências explícitas e resultado parcial quando faltam classificações; depreciação e rateio por canal permanecem fora do escopo.

# 0.6.0 — Despesas por competência
- Plano hierárquico por natureza, regras configuráveis e seleção manual prioritária.
- Despesa gera obrigação sem caixa; pagamento, estorno e cancelamento integrados.
- Classificação histórica, correção com motivo/revisão e não classificados visíveis.
- Recorrência mensal com prévia, prevenção de duplicidade e encerramento sem apagar ocorrências.
- Relatórios HTML/API por competência com permissões independentes; proteção PostgreSQL e teste Chromium.
- DRE completa e recorrência agendada permanecem futuras.

# 0.5.0 — Financeiro
- Contas com abertura protegida, títulos vinculados a compras/vendas, pagamentos parciais e recebimentos.
- Juros/descontos explícitos, idempotência, revisão otimista, guarda financeira no cancelamento e estornos rastreáveis.
- Transferências previstas/realizadas, caixa diário derivado do livro e alerta de pendências sem conta.
- Permissões independentes para operação e saldos; PostgreSQL protege histórico e equilíbrio das transferências.
- Despesas por competência/plano de contas e DRE seguem nas próximas fases.

# 0.4.0 — Compras e fornecedores
- Fornecedores editáveis/inativáveis, compra manual com vários itens, documentos únicos e parcelas.
- Confirmação de compromisso separada de recebimento físico, rateio exato em centavos, custo médio e histórico preservado.
- Cancelamento seguro, relatórios de fornecedor com permissão própria e testes de transferência Mercadovet → Full.
- Liquidações bancárias permanecem na Fase 5. Validação e evidências no PR da fase.

# 0.3.0 — Vendas manuais
- Estoque padrão configurável e troca no lançamento; locais adicionais.
- Edição de alíquota com vigência e recálculo retroativo auditado conforme solicitação do usuário.
- Taxas extras nome/valor, incluindo MDR, com impacto na margem.
- Canais e regras tributárias configuráveis, NF/série únicas, rascunhos e múltiplos itens.
- Confirmação/cancelamento atômicos, snapshots de CMV, composição e imposto; margem individual protegida por permissão.
- Retorno pelo valor original preservando compras posteriores, proteção PostgreSQL de histórico, testes de concorrência e navegador.
- Fase 3 com validação PostgreSQL/Chromium registrada no PR #12; compras/financeiro permanecem futuros.

# Changelog
## 0.1.0 — Fundação (15/09/2026)
- Arquitetura, modelo alvo em Mermaid, ADRs e contratos por domínio.
- Decisão de entrada manual e corte em 15/09/2026.
- Django 5.2.17, PostgreSQL, Docker, configuração por ambiente.
- Login/logout, troca de senha, grupos/permissões granulares e controles backend.
- Empresa, margem mínima configurável, auditoria e migração inicial.
- Layout Mercadovet claro/escuro, navegação por permissão.
- Testes PostgreSQL e CI; scripts de backup/teste de restauração.
- Módulos transacionais e relatórios permanecem no backlog. Sem migração da planilha.

## Decisão de estoque inicial — 15/09/2026
- Autorizado usar o estoque da planilha como base atual de desenvolvimento, com abertura na data de corte e ajustes posteriores auditados.
- Alteração documental: carga e tela de ajustes permanecem na Fase 2, sem carga de dados nesta alteração.

## 0.2.0 — Produtos e estoque
- Cadastro manual, pesquisa SKU/nome, paginação, categorias, marcas, locais e inativação.
- Abertura, custo médio, entradas, saídas, ajustes, correção de custo, transferências, fracionamento e kits virtuais.
- Livro imutável, operações atômicas/idempotentes, estornos e auditoria.
- Carga inicial validada/idempotente da aba ESTOQUE MVET e conferência do livro.
- Interface Mercadovet e autorização de custos no backend.
- Testes de domínio, HTTP, permissões, importação, concorrência PostgreSQL e fluxo visual com dados sintéticos.
# 18/09/2026 — acessos e exportações

- Políticas individuais permitidas/negadas pelo master com auditoria e controle de edição concorrente; separação de faturamento, custos, margens e relatório detalhado.
- Controles específicos de confirmação, cancelamento, estoque, pagamentos/recebimentos, transferências, tributos e recorrência.
- Excel/PDF nos relatórios existentes, projeções autorizadas, todos os registros do filtro, limites explícitos e proteção contra fórmulas em texto externo.
- Estudo público da API Bling: pré-preenchimento de NF/SKU/canal e conciliação de movimentos; nenhuma conexão real ativada.

## 28/09/2026 — Relatório por canal, compras Bling e caixa
- Vendas: filtros compactos, cartões por canal/empresa, subtotais completos e layout responsivo sem barra horizontal; composição detalhada expansível.
- Compras: consulta NF-e de entrada no Bling, conferência de fornecedor/produtos/frete/parcelas e rascunho idempotente. Migração aditiva com proteção do vínculo.
- Caixa: resumo do período inclui compromissos sem banco no consolidado e acesso à baixa de pagamentos futuros com data efetiva; regressões de pagamento parcial, estorno, reagendamento e retroatividade.

## 29/09/2026 — Compras a pagar compactas
Filtros compactos em compras; tabela por parcela com produtos, linhas alternadas e totalizações de saldo por mês/fornecedor. Padrão de hoje em diante, sem excluir histórico nem classificar datas passadas como vencidas nesta tabela. Sem mudanças de schema ou de lançamentos.

## Compras Bling — unidade local e rejeição (29/09/2026)
Unidade cadastrada no MVet prevalece; quantidade e preço da nota mantidos sem conversão. Rejeitar nota retira documentos sem compra vinculada das pendências; filtro Rejeitadas permite reabrir. Reconsulta preserva rejeição. Compras existentes seguem cancelamento próprio. Ver ADR 0024.

## 05/10/2026 — Dashboard inicial e revisão visual
Indicadores como início autorizado, mês completo com datas visíveis, cartões de receita/resultado/compras/bancos/estoque respeitando permissões. Menu por função, filtros e espaçamentos compactos globais, navegação móvel recolhível. Caixa como matriz banco × dia, entradas/saídas/saldo, visões realizado/previsto e totais, mantendo histórico e paginação. Ver docs/DASHBOARD.md.

## 10/10/2026 — financeiro, plano de contas e relatórios
- Baixas aceitam data futura, reservam o principal e afetam projeção/realizado na data correta. Estorno futuro sem crédito fictício hoje.
- Plano Mercadovet instalado de forma aditiva pelo atualizador; principal e juros separados, pendências explícitas e depreciação manual sem conta a pagar.
- Cartões: total primeiro, demais por valor decrescente e opção persistente de ocultar valores.
- Vendas exportadas em todos os canais, com resumo e seções/abas por canal, preservando filtros de período/NF/situação e permissões.

## 2026-10-11 — Estoque, preço da loja e caixa
- Markup inicial 35% apenas loja, geral ou individual exclusivo master, coluna de preço e exportação/consulta sem revelar custos ao operador.
- Conciliação de posição por depósito: prévia, diferenças auditadas, produtos novos, base completa/parcial, movimentos posteriores preservados e proteção contra duplicação/concorrência.
- Caixa de hoje até hoje+15, destaque no dia atual e lançamentos manuais futuros sem antecipar saldo realizado.

## 2026-10-11 — Distribuição diária no CRM
- Primeiros contatos aguardam distribuição em vez de lotar pendências futuras; cadastros e histórico preservados.
- Master define limite diário total, início e pausa. Seleção aleatória persistida, sem duplicar cota em acessos concorrentes.
- Retornos seguem agenda própria e não consomem o limite; indicadores distinguem fila de novas pendências.

## 2026-10-11 — Revisão funcional transversal
- Vencimento renegociado consistente entre financeiro, compras, fornecedores e exportações, preservando o original.
- Quadro Excel do caixa respeita visão realizada/projetada; página evita calcular o livro duas vezes.
- Validação de valores extremos e motivo de cancelamento para despesas sem caixa.
- Escopo das contas nos indicadores explicitado; revisão documentada em docs/FUNCTIONAL_REVIEW_2026_10_11.md.

## Correção — desconto do XML Bling
- Conferência de vendas preenche o desconto explícito do XML; compras preservam o desconto por item sem duplicar o desconto geral. Ajustes manuais continuam prioritários.


### Conferência Bling: filtros e correção em massa (22/10/2026)

Comparar saldos, preços ou ambos, com filtro imediato das diferenças do campo escolhido e preservação da consulta salva. Seleção de até 50 produtos da página, campo e destino explícitos, prévia e confirmação do lote. Execução sequencial por produto no navegador, com resultado individual, revalidação e proteção contra reenvio; manter a página aberta até concluir. Erros de transporte interrompem os itens seguintes, preservando os concluídos. SKU exato e único determina o vínculo; unidade diferente não bloqueia nem converte valores. Consultas antigas bloqueadas por unidade precisam de nova consulta explícita.


### SKUs encontrados e paginação após filtros (22/10/2026)

Filtro Todos/Encontrados/Não encontrados no Bling. Existência do SKU é independente de erros de saldo, unidade ou duplicidade; erro não significa ausência. A consulta completa é feita em pequenos lotes com progresso no navegador, preservando o resultado anterior até concluir. Após a consulta, filtros e paginação usam apenas os dados salvos, em ordem numérica de SKU, até 50 resultados filtrados por página. Trocar filtro volta à primeira página. Consulta antiga de uma página é preservada com aviso para atualização explícita.


### Valor manual na definição de comissão (22/10/2026)

A tela Definir comissão da venda aceita valor total manual em R$, opcional. Preenchido, prevalece sobre o percentual; vazio mantém a prioridade percentual manual, padrão do comissionado e padrão global. Zero é valor explícito. O total manual é auditado, rateado nas parcelas e substitui a comissão da venda sem duplicar custo. Funciona também sem percentual configurado.


### Fornecedor nos pagamentos pendentes (23/10/2026)

Saldos e fluxo de caixa e pendências da conta exibem fornecedor/favorecido abaixo da descrição. Usam o nome gravado no título; para título antigo vazio de compra, consultam o fornecedor da compra vinculada. Títulos de compra continuam gravando o nome do fornecedor em cada parcela e rejeitam fornecedor sem nome. Não altera valores, vencimentos ou liquidações.

## Transferência de vários produtos (24/10/2026)

Produtos e estoque ou Movimentar estoque → Transferir vários produtos. Informe origem, destino, data e motivo/documento uma vez; busque cada SKU/nome e preencha sua quantidade. Até 200 produtos simples ativos, uma linha por SKU; Excluir retira a linha. Confirmação cria uma única transferência com todos os movimentos e estorno conjunto pelo histórico. Saldo insuficiente ou qualquer item inválido bloqueia o envio inteiro. Validação usa saldo atual sob lock; reenvio idêntico não duplica. Permissões operate_stock e transfer_stock, sem exigir acesso a custos.

## 26/10/2026 — resultado antes do imposto e ordem dos cartões

Dashboard inclui Resultado antes do imposto: receita operacional − CMV histórico efetivo − frete pago − taxas. Segue período/canal e exige view_margins. Não deduz imposto, DIFAL, comissão, extras/MDR ou outros custos; não substitui contribuição ou resultado da empresa. Cartões podem ser reorganizados pela alça (mouse/toque) ou setas do teclado. Ordem salva no banco por usuário, preservada entre acessos/dispositivos; novos cartões autorizados aparecem ao final. Falha de salvamento é exibida com opção de tentar novamente. Migração aditiva DashboardPreference, sem alterar lançamentos.

26/10/2026: arraste dos cartões destaca o destino e só reorganiza ao soltar, permitindo movimentos horizontais/verticais sem perder a captura do ponteiro durante a troca de posição. Alça de quatro direções; teclado sobe/desce por linha e move esquerda/direita por posição. Testes de navegador cobrem ambos os lados e persistência após recarga.
