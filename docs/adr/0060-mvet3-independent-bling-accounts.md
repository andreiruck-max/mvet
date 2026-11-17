# ADR 0060 — MVet 3.0: uma conta Bling independente por empresa

**Data:** 17/11/2026
**Estado:** definição aprovada para implementação futura no MVet 3.0; NÃO implementado no MVet 2.0.

## Contexto

Mercadovet e MVet Agro possuem CNPJs próprios e cada uma utilizará **uma conta independente no Bling**. O MVet 2.0 opera com `BlingConnection(pk=1)`, `BLING_ISSUER_CNPJ` único, agendamentos por tipo sem empresa e rotinas que presumem um único token. O MVet 3.0 precisa reaproveitar todas as funções Bling para ambos os CNPJs sem cruzar dados.

## Decisão

1. Criar `BlingConnection.company` com titularidade exclusiva por CNPJ (`OneToOneField` recomendado), validando `issuer == company.cnpj`.
2. Cada conta Bling terá sessão de autorização OAuth, access/refresh tokens, expiração, bloqueio de atualização, desconexão e histórico de eventos INDEPENDENTES. A configuração do aplicativo OAuth (`client_id` e `client_secret`) poderá eventualmente ser compartilhada por ambas as autorizações se o Bling permitir; isso **não** torna a conta, os tokens ou os dados compartilhados.
3. Toda API de integração aceitará conexão/empresa explicitamente. Proibidos `pk=1`, seleção global de token e consulta sem escopo. O `state` de OAuth será de uso único e vinculado de forma íntegra a empresa/usuário/tentativa.
4. Notas, vendas, compras, estoque, preços, catálogo, depósitos, contas bancárias, extratos, filas, workers, agendamentos, preferências, caches e logs serão separados por empresa e conexão. Identidade externa é `(connection, external_id)`.
5. Pedido interempresa será criado **na conta Bling da fornecedora**, em qualquer direção, mediante confirmação explícita, com garantia de idempotência, persistência e tratamento de resposta incerta.
6. A visão Grupo consolida dados no MVet, sem utilizar uma falsa “conexão Bling do grupo”. Duas contas Bling não implicam automaticamente estoque comercial compartilhado. Funcionalidades externas Bling Multiempresas, depósito virtual e marketplace exigem configuração e homologação próprias.
7. Uma conta não pode alterar configurações, autorizações, cadastros, lançamentos ou saldos de outra. Na homologação, manter ambas as integrações reais desligadas/sem credenciais em bancos clonados.

## Alvos técnicos

- `apps/integrations/models.py`: `BlingConnection`, `BlingSchedule`, `ReviewDefaults`, `BlingComparisonCache`, notas, aliases, banco e corridas;
- `apps/integrations/bling.py`: `configured`, `authorize`, `disconnect`, `get`, `read`, `sync_page`, `refresh_invoice`;
- `apps/integrations/scheduling.py`, `bank_services.py`, `services.py`, `purchase_services.py`, `stock_comparison.py` e todas as views/formulários e comandos;
- `config/settings.py`, ambiente, auth/permissões, testes de sessão/callback e isolamento financeiro/estoque.

## Testes de aceite

- OAuth Mercadovet e MVet Agro com callbacks cruzados impedidos; duas credenciais/token stores distintos.
- Expirar/desconectar/reautorizar a conta MVet Agro não interrompe Mercadovet.
- Documento com mesmo número e série em contas diferentes não colide, mas identidade NF-e permanece única conforme chave.
- Produto com mesmo SKU e IDs externos diferentes mapeia corretamente.
- Agendamentos e filas de uma empresa não alteram a outra.
- Consulta de banco de uma empresa não pode ser associada à conta financeira da outra.
- Pedido interempresa sai na conta do CNPJ fornecedor, nos dois sentidos; timeout não duplica pedido.
- Seleção de Grupo não permite escrita remota.
- MVet 2.0 segue intacto na branch `main`.

**Plano e dependências:** `docs/MVET_3_0_HANDOFF_MULTIEMPRESA.md`. Implementar em PR específica baseada em `develop/mvet-3.0`, depois de fundação, escopo empresarial e estoque, sem deploy em produção.
