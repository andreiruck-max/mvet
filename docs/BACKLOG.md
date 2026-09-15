# Backlog
Atualização: 15/09/2026. A entrada inicial será manual por decisão do usuário.

| Fase | Entrega / aceite | Estado |
|---|---|---|
| 0 | Diagnóstico, arquitetura, ERD, ADRs e regras de corte | Documentado |
| 1 | Django/PostgreSQL/Docker, login, permissões, layout, auditoria, configuração, testes | Em desenvolvimento |
| 2 | Produtos, locais, abertura manual, entradas/saídas, média, fracionamento e kits | Planejado |
| 3 | Venda manual com múltiplos itens, SKU/nome, snapshots, confirmação, cancelamento, filtros | Planejado |
| 4 | Fornecedores, compra manual, recebimento, rateio e parcelas | Planejado |
| 5 | Contas, pagar/receber, liquidações, transferências, saldo diário/projetado | Planejado |
| 6 | Despesas por competência, plano hierárquico, regras determinísticas | Planejado |
| 7 | Dashboard, comparativo por canal e DRE após validação das fontes | Planejado |
| 8 | Notificações e preferências, comando agendado | Planejado |
| 9 | Importações e integrações com preview, idempotência e rollback seguro | Evolução opcional |

## Não confundir com entrega
ERD e documentação de contratos não significam módulos funcionando. Cada fase exige UI, migrations, autorização, testes aprovados e commits remotos.
Importação integral da planilha foi retirada do caminho crítico.

## Evolução
Recorrência, conciliação, devoluções parciais, reservas, kits físicos, custos de embalagem/mão de obra, integrações de canais/bancos e automação de backup externo.
Milestones nativos e proteção de branch ainda não configurados: as ferramentas atuais não expõem esses ajustes.
