# ADR 0062 — Conferência de compra sem declarações obrigatórias

Status: aceito por solicitação explícita do usuário em 20/11/2026 (MVet 2.0).

Remover as caixas de declaração de destinatário/finalidade e revisão contábil da importação. A importação é uma ação explícita que salva rascunho; confirmar e receber continuam ações autorizadas e auditadas. A confirmação deixa de exigir `taxes_reviewed`, inclusive para rascunhos antigos. O campo histórico permanece no banco, sem atribuir uma revisão contábil que não ocorreu.

Preservar todas as verificações existentes de documento, fornecedor, finalidade conhecida, CFOP, situação, composição fiscal, créditos, NCM, parcelas, permissões e duplicidade. Nenhum tributo passa a ser crédito automaticamente. A auditoria nova identifica `review_method=explicit_draft_import`, em vez de declarar que houve conferência externa.

Essa decisão substitui a exigência de checkbox descrita na ADR 0061 e na documentação anterior de compras. Não altera compras confirmadas, custo histórico, dados fiscais nem critérios de capitalização. Não adiciona comprovação automática do destinatário quando não fornecida pela fonte.

A tela organiza identificação, frete/descontos e tributos em seções. Em larguras de popup os itens viram cartões de duas colunas; no celular, uma coluna. Ajuda vem depois do campo, sem deslocar os controles de cada linha.
