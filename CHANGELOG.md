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
