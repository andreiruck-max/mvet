# ADR 0060 — Movimentação no modal, conferência e retiradas

17/11/2026 — solicitado pelo usuário, preparado fora da main.

A conta permite operar pelos serviços existentes dentro do modal; conclusão retorna ao extrato e fechamento atualiza a origem. Não duplica nem altera o livro financeiro. Conferência Bling permite selecionar outra conta MVet, preservando período; isso não modifica o vínculo externo. Abrir a conferência solicita atualização por POST/CSRF mesmo se atualização automática da ficha estiver desativada. Consulta segue em segundo plano e reutiliza tarefas ativas. GET continua sem efeitos. Permissões preservadas.

Indicador de saldo igual exige consulta mais recente concluída hoje e cobertura integral desde a abertura externa, diferença zero e abertura informada. Falhas, tarefas pendentes e histórico incompleto nunca recebem check verde. Compara saldo líquido, não concilia cada movimento.

WITHDRAWAL é classificação gerencial de título para retirada/distribuição de sócio, fora da DRE. Relatório soma lançamentos bancários efetivos por data, conta, mês e favorecido, incluindo estornos com sinal contrário na data do estorno. Pagamentos parciais não contam principal ainda pendente. Créditos podem registrar devolução. Juros mantêm o tratamento financeiro vigente na DRE. Movimentos genéricos antigos exigem reclassificação auditada; não se infere retirada pela descrição.
