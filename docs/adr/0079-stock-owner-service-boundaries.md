# ADR 0079 — Fronteira empresarial dos serviços de estoque

Serviços execute, reverse e transfer_batch aceitam company_id, validam o
contexto antes inclusive de devolver replay e persistem o proprietário.
Nesta transição somente 1 é permitido; grupo e empresa secundária falham
explicitamente sem retornar ou consumir estoque da Mercadovet.

_value_out, _date, _apply e recuperação de custo anterior filtram o proprietário.
_apply usa a empresa da operação para saldo e movimento. check_inventory
compara cada saldo ao livro de seu proprietário e detecta incoerência entre
operação e movimento. Locks, fingerprints legados e aritmética não mudam.

Ainda não habilita Agro: unicidade produto/local, projeções Product, referências
em compras/vendas, contagens, importações, planejamento e consultas precisam
ser adaptadas. Remover a trava isoladamente é incorreto. Esta etapa preserva
a API legada com default 1; contexto explícito inválido jamais vira default.

Testes exercitam rejeição sem efeitos, replay no grupo negado e transferência
primária idempotente. Regressão integral PostgreSQL/Chromium no CI.
