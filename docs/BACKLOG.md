# Backlog

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
