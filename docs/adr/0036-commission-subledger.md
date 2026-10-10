# ADR 0036 — Comissões por recebimento e quitação rastreável

Status: aceito, 10/10/2026.

A comissão nasce como custo previsto da venda, calculado sobre produtos menos descontos, excluindo frete. O percentual (manual/pessoa/global) é snapshot. A liberação acompanha recebimentos proporcionais das parcelas, em livro imutável separado; o pagamento aloca liberações, sem alterar o custo por competência novamente.

O módulo não reintroduz contas a receber automáticas (ADR 0022) nem movimentos bancários implícitos. Recebimento e pagamento são evidências manuais, claramente identificadas na interface. Venda confirmada escolhida para comissionamento recebe plano único. O custo usa o campo Sale.commission existente por correção auditada, evitando duplicar resultado.

Alteração do percentual/total gera ajuste de liberação hoje e correção de custo da venda. Alterações da base na venda propagam ao plano, mantendo cronograma original e evidenciando divergências. Cancelamento, recuperação e estorno têm contrapartidas; pagamento prévio gera compensação negativa, nunca exclusão de histórico. Apuração usa eventos até o encerramento e pagamentos por data; saldo de competência e caixa pago são colunas distintas.

Operações compartilham mutex do domínio e possuem idempotência. Funcionário só consulta sua pessoa vinculada; gestor de comissões opera o módulo sem receber acesso a custos/caixa/DRE. Livro protegido por triggers PostgreSQL. Não há migração de negócios/valores existentes ou automatismo sobre vendas não selecionadas.
