# ADR 0086 — Integridade empresarial do livro no PostgreSQL

Após permitir posições internas de dois proprietários, uma FK simples ainda
poderia relacionar movimento e operação de empresas diferentes. A migration
0015 acrescenta gatilhos de INSERT: empresa do movimento deve coincidir com a
operação; empresa do estorno deve coincidir com a operação original.

Não substitui autorização, locks ou validação do serviço. FKs existentes continuam
validando existência das referências. Gatilhos de UPDATE/DELETE imutáveis são
preservados; nenhuma linha histórica é atualizada ou excluída. O auditor continua
verificando registros antigos, pois novos gatilhos não validam retroativamente.

Reversão da migration remove apenas os novos gatilhos/função, sem modificar dados.
Testes PostgreSQL tentam inserir vínculos cruzados diretamente no ORM e exigem
rejeição do banco. Os fluxos válidos são cobertos pela regressão de estoque e
pelos testes de aritmética empresarial. Não habilita operações da Agro.
