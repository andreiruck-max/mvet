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
