# ADR 0069 — Identidade empresarial do livro de comissões

Planos, parcelas, comandos, liberações, pagamentos e alocações recebem FK company obrigatória e protegida. Default constante Mercadovet e constraints transitórias bloqueiam operações secundárias enquanto os serviços não forem contextualizados. Cadastros de comissionados e configuração padrão permanecem na etapa seguinte.

DDL aditivo sem UPDATE de histórico e sem remover gatilhos. Não altera bases, percentuais, compensações, competência, custo da venda nem pagamentos; não gera lançamento bancário. MODELO ainda não habilita multiempresa operacional.

Testes exercitam liberação e pagamento parcial, proprietários e ausência de efeito bancário. Ensaio de migration compara todos os campos históricos, incluindo termos dos eventos, parcelas e alocações, preserva os gatilhos e confirma imutabilidade. Exigir PostgreSQL e navegador antes da integração. Sem produção MVet 2.0.
