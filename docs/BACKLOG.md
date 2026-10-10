## 10/10/2026 — CRM / Comercial
Primeira versão implementada com carteira, recorrência, histórico, aprovação master, importação validada e indicadores. Validação PostgreSQL/Chromium/Windows registrada no PR. Instalação local e liberação de usuários pelo Master permanecem etapas operacionais. Sem WhatsApp automático, IA, funil de oportunidades ou cadastro fiscal; extensões futuras separadas. Ver docs/CRM.md.

## 09/10/2026 — Navegação, compras e canais
Pacote implementado: submenus diretos, imposto no Dashboard, relatório de vendas com canais ativos clicáveis e ordem crescente, abas de compras/parcelas, resumo por fornecedor ordenado com contagem/média, divergência exata e antecipação explícita. Validação PostgreSQL/Chromium/Windows e integração acompanhadas no PR. Dados locais não alterados nesta sessão.

# Correção de canal e depósito da venda — 09/10/2026
Master pode usar Corrigir venda para alterar canal e depósito junto aos valores. Troca de depósito registra estorno e nova saída auditados; CMV histórico preservado e diferenças de estoque no resultado da data atual. Migration 0012; ADR 0034. Sem alteração automática de vendas existentes ou instalação local.

# Correção Bling — Emitida DANFE (09/10/2026)
Busca padrão por Autorizada + Emitida DANFE; confirmação e recuperação aceitam status 6. Impressão não gera divergência comercial nem duplicação. ADR 0033. Busca direta vazia na API ainda em diagnóstico; sem instalação local automática.

# Backlog
Novo pacote (ADR 0029): calendário, notas por série/valor/cliente, regra tributária sugerida e estoque negativo. Usuário autorizou em 08/10/2026 integrar cada alteração à main após validação. Instalação local/PowerShell somente ao fim do pacote, após OK. Validação PostgreSQL e Chromium em andamento.
Recuperação de venda cancelada por engano e correção de Taxas: implementação em validação, com auditoria, preservação de snapshots e nova saída do estoque. Sem alteração automática de venda real por migration. ADR 0028.

Correção de compatibilidade do atualizador com stderr nativo do PowerShell 5.1; validação adicional em runner Windows. Sem mudança de dados ou aplicação.

## Fechamento do pacote — 07/10/2026
Últimos ajustes autorizados: plano de contas com sugestão editável, nova despesa compacta com favorecido/fornecedor opcionais e categorias pesquisáveis. Pacote PR 33 liberado pelo usuário para integração após validação; a instalação Windows é feita por `scripts/update_windows.ps1`, com backup restaurado em banco isolado antes de migrations. A execução na máquina da empresa permanece a cargo do usuário; não confundir integração ao Git com implantação local.

## Complemento financeiro — 07/10/2026
Quadro bancário com 15 dias desde ontem, sem páginas de dias, bordas/cores e cabeçalho corrigidos; página de conta com extrato, entrada/saída, agendamento, transferência e edição. Inativas ocultas do quadro com histórico preservado. Em validação no mesmo PR 33, sem implantação local. ADR 0027.

## Complemento do pacote — 07/10/2026
Vínculos de venda sem unidade externa, confirmação única, estoque com saldo por padrão e planejamento de compra implementados (ADR 0026). Manter no PR 33 junto às compras flexíveis até terminar o pacote; sem implantação local nesta etapa.

## Pacote em preparação — 06/10/2026

Seleção em massa nas filas Bling, compras mistas (estoque/financeiro), cadastro de produto durante importação e bonificação sem pagamento: implementados, em validação. Ver ADR 0025. Manter separado da instalação local até reunir as próximas alterações do usuário. Não limpar notas reais por migration; usar a ação reversível na fila após implantação.

## Ampliação — acessos e arquivos

[PR #18](https://github.com/andreiruck-max/mvet/pull/18): políticas individuais pelo master e exportações Excel/PDF nos módulos existentes. Entregue e integrado: 236 testes PostgreSQL e 9 Chromium aprovados. Não adiar exportações para a Fase 9. Bling: importação assistida de NF/SKU e OAuth implementados nesta etapa; validação PostgreSQL/Chromium registrada no [PR #20](https://github.com/andreiruck-max/mvet/pull/20), com homologação real ainda pendente. Conciliação financeira continua futura, sem promessa de saldo bancário direto. ADR 0015 define fila separada de conferência, custos de marketplace manuais, CMV exclusivo do MVet e cancelamentos independentes; implementação preserva escolhas locais e não reativa vendas canceladas. Ver BLING_SETUP.md para os limites concretos.
Atualização: 18/09/2026. Operação manual, com carga inicial restrita ao estoque autorizada pelo usuário.

| Fase | Entrega / aceite | Estado |
|---|---|---|
| 0 | Diagnóstico, arquitetura, ERD, ADRs e regras de corte | Documentado |
| 1 | Django/PostgreSQL/Docker, login, permissões, layout, auditoria, configuração, testes | Implementado no PR #2; CI PostgreSQL aprovado; instalação destino pendente |
| 2 | Produtos, locais, abertura, entradas/saídas, ajustes, média, fracionamento e kits | Concluído no PR #11; 58 testes PostgreSQL e 1 teste Chromium aprovados |
| 3 | Venda manual com múltiplos itens, SKU/nome, snapshots, confirmação, cancelamento, filtros | Concluído no PR #12; evidências PostgreSQL/Chromium no PR; inclui estoques, vigências e taxas extras |
| 4 | Fornecedores, compra manual, recebimento, rateio e parcelas | Concluído no PR #13; 128 testes PostgreSQL e 3 Chromium aprovados; pagamento integrado na Fase 5 |
| 5 | Contas, pagar/receber, liquidações, transferências, saldo diário/projetado | Concluído no PR #14; 158 testes PostgreSQL e 4 Chromium aprovados |
| 6 | Despesas por competência, plano hierárquico, regras determinísticas e recorrência mensal | Concluído no PR #15; 187 testes PostgreSQL e 5 Chromium aprovados |
| 7 | Dashboard próximo das planilhas, vendas tabulares, caixa por dia, compras a pagar, comparativo por canal e DRE | Concluído no PR #16; 206 testes PostgreSQL e 6 Chromium aprovados |
| 8 | Notificações, preferências, comando agendado e evidências de backup | Concluído no PR #17; 219 testes PostgreSQL e 7 Chromium aprovados; agendamento no destino pendente |
| 9 | Importações e integrações com preview, idempotência e rollback seguro | NF Bling assistida implementada no PR #20; homologação real e conciliação financeira pendentes |

## Não confundir com entrega
ERD e documentação de contratos não significam módulos funcionando. Cada fase exige UI, migrations, autorização, testes aprovados e commits remotos.
Importação integral da planilha foi retirada do caminho crítico.

## Evolução
Recorrência agendada/outras periodicidades, conciliação, devoluções parciais, reservas, kits físicos, custos de embalagem/mão de obra, integrações de canais/bancos e automação de backup externo.
Milestones nativos e proteção de branch ainda não configurados: as ferramentas atuais não expõem esses ajustes.

## Issues
- [Fase 1](https://github.com/andreiruck-max/mvet/issues/1)
- [Fase 2 — estoque](https://github.com/andreiruck-max/mvet/issues/3)
- [Fase 3 — vendas](https://github.com/andreiruck-max/mvet/issues/4)
- [Fase 4 — compras](https://github.com/andreiruck-max/mvet/issues/5)
- [Fase 5 — financeiro](https://github.com/andreiruck-max/mvet/issues/6)
- [Fase 6 — despesas](https://github.com/andreiruck-max/mvet/issues/7)
- [Fase 7 — indicadores e DRE](https://github.com/andreiruck-max/mvet/issues/8)
- [Fase 8 — notificações](https://github.com/andreiruck-max/mvet/issues/9)
- [Fase 9 — integrações opcionais](https://github.com/andreiruck-max/mvet/issues/10)

A fundação foi publicada por plugin após indisponibilidade do ambiente local. O código de módulos transacionais iniciado localmente não foi incorporado, pois não foi validado. A branch remota é a fonte de verdade.

## Atualização autorizada — estoque inicial
Usar somente o estoque de ERP Mvet(2).xlsx como base atual de desenvolvimento, com abertura em 15/09/2026. A Fase 2 inclui carga validada/idempotente e ajustes positivos, negativos e de custo auditados. Demais operações continuam manuais. Carga e interface implementadas na Fase 2. Ver docs/INVENTORY.md e ADR 0006.

PR #20 também inclui vendas manuais sem NF, rascunho incompleto do master, imposto zero e ajuste explícito da receita (ADR 0016). Confirmação mantém integridade de estoque e os ajustes refletem recebível, DRE e exportações.

## Preparação da instalação — 19/09/2026
PR #20 integrado à main. Adicionado comando check_installation e roteiro INSTALLATION_CHECKLIST.md para triagem e aceite no destino. Não substitui instalação presencial, HTTPS, restauração ou homologação real do Bling.

Correção da homologação Bling (21/09/2026): finalidade ausente passa à conferência humana explícita/auditada, preservando bloqueios conhecidos e snapshots externos (ADR 0017). Validação CI registrada no PR da correção.

Produtividade Bling: busca de período com paginação automática sequencial, progresso, interrupção e retomada na aba; conferência individual separada. Não exige percorrer manualmente grupos de cinco notas.

Posição inicial por depósito: comando `import_inventory_locations`, testes e ADR 0018. Execução e validação no banco da empresa permanecem necessárias. Sem nova tela de upload.

MVet 1.5: navegação e valorização por depósito, busca SKU exata, ordenação numérica e paginação de 50 implementadas. Custo local nas operações e migração pelo livro conforme ADR 0019. Aceite PostgreSQL e navegador registrado no PR; implantação no computador da empresa é etapa separada.

MVet 1.5: contagem física individual por depósito, filtro positivo, formatação de milhares e retorno contextual implementados. Migração 0007 remove apenas Full legado sem vínculos; locais com saldo/histórico/padrão/referências são preservados para conciliação específica. Testes de aplicação e navegador registrados no PR.

- Correção UN/UNID: abreviações equivalentes no SKU automático e vínculo manual, sem conversão de quantidade, alteração do documento recebido ou de históricos.

## Atualização de 25/09/2026 — ADR 0022
Novas vendas não geram contas a receber; títulos anteriores e liquidações são preservados. Compras/despesas continuam gerando contas a pagar. Bling: topo compacto, atalho ao relatório, sugestões Full/demais lojas configuradas em Conexão Bling, valores monetários com duas casas e zeros iniciais, frete recebido e pago sugeridos iguais ao valor da nota e editáveis. Desconto manual em zero quando não fornecido pelo contrato. Confirmação pelo botão, sem caixa genérica; finalidade ausente ainda exige declaração. Imposto pela regra tributária, sem campos manuais na conferência.

### Entrega de 28/09/2026
- Relatório compacto de vendas por canal, cartões de totais do período e composição expansível.
- Importação assistida de NF-e de entrada do Bling para rascunho de compra, incluindo parcelas.
- Acesso a baixa antecipada e previsão consolidada com pendências sem banco.
- Não inclui descoberta SEFAZ, conversão de embalagem, recebimento parcial ou baixa bancária automática.

### 29/09/2026
Compras com filtros compactos; compras a pagar no formato de planilha, linhas alternadas, produtos, 50 parcelas/página, totais geral/mensal/fornecedor. Padrão de hoje em diante com histórico consultável, sem classificar datas passadas como vencidas.

## Compras Bling — unidade local e rejeição (29/09/2026)
Unidade cadastrada no MVet prevalece; quantidade e preço da nota mantidos sem conversão. Rejeitar nota retira documentos sem compra vinculada das pendências; filtro Rejeitadas permite reabrir. Reconsulta preserva rejeição. Compras existentes seguem cancelamento próprio. Ver ADR 0024.

## 05/10/2026 — Dashboard inicial e revisão visual
Indicadores como início autorizado, mês completo com datas visíveis, cartões de receita/resultado/compras/bancos/estoque respeitando permissões. Menu por função, filtros e espaçamentos compactos globais, navegação móvel recolhível. Caixa como matriz banco × dia, entradas/saídas/saldo, visões realizado/previsto e totais, mantendo histórico e paginação. Ver docs/DASHBOARD.md.
## 08/10/2026 — Vendas e origens da DRE
Implementado no novo pacote: grade de vendas por canal com produtos/quantidades, colunas condicionais, cabeçalho/total fixos, recolhimento e negativos destacados. Detalhamento reconciliado da DRE e acesso às origens somente pelo master. Validação PostgreSQL/Chromium registrada no PR; instalação no PC depende do OK final do usuário.
## 08/10/2026 — Correção de lançamentos e navegação
Correção auditada de valores de vendas confirmadas, recuperação destacada, busca direta Bling por número/série, digitação monetária por centavos e atalhos dos indicadores implementados. Consulta real das NFs ausentes e correção dos valores empresariais serão realizadas pelo usuário após a instalação; não há acesso ao banco local nesta sessão.
## 09/10/2026 — Filtros, desconto de item e cadastros na importação
Novo pacote: filtros automáticos em vendas, NF crescente por data/canal, desconto de compra por linha, fornecedor novo junto com importação e atalhos explícitos para crédito/débito da conta. Migration adiciona desconto zero sem recalcular histórico; ADR 0032. Validação e integração registradas no PR do pacote. Instalação no PC e preenchimento dos documentos reais são etapas locais, não executadas nesta sessão.
