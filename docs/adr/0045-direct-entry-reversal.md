# ADR 0045 — Estorno de lançamento bancário direto

Data: 16/10/2026. Status: aceito.

Novo crédito/Novo débito usa título auxiliar e liquidação atômica. Esse título não representa um compromisso independente. Reabri-lo no estorno produz previsão indevida, embora o extrato realizado esteja correto.

O estorno do atalho, identificado por uuid5(title.key, account-entry-settlement), cancela também seu título auxiliar após zerar o principal. Não exige permissão adicional de cancelamento de títulos: integra o estorno já autorizado. Preservar todos os lançamentos e auditoria. Substitui a reabertura do título para lançamentos diretos descrita na ADR 0038; obrigações independentes continuam seguindo ADR 0037.

Reparo retroativo em todas as contas: somente título manual, não de abertura, sem vínculo com compra/venda/despesa, aberto com principal liquidado zero e revisão 2; uma única liquidação original, UUID exato, principal integral e estorno realizado vinculado. Não inferir identidade por nome, valor, conta ou texto. Registros reagendados/reutilizados são preservados. Não apagar movimentos, não alterar saldo inicial, não gerar estorno adicional. Reparo idempotente e auditado pelo autor do estorno; rollback de código não reabre previsões indevidas.

Testes cobrem crédito/débito, múltiplas contas, data futura, repetição, pendência independente e reparo legado sem alteração do livro. Consolidado previsto e realizado continuam semanticamente distintos quando existem compromissos legítimos.
