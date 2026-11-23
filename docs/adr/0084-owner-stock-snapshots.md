# ADR 0084 — Posição do proprietário antes/depois do movimento

StockMovement recebe quatro campos opcionais: quantidade e valor da empresa
proprietária antes e depois do movimento, somando os depósitos do SKU dessa
empresa. _apply calcula o snapshot sob os locks/transação existentes; custo
médio para saída continua local, sem usar a média agregada do grupo.

Colunas são nulas no histórico, sem backfill inventado nem UPDATE de livro
imutável. Novos movimentos via serviço registram os quatro campos. Constraint
exige todos preenchidos ou todos nulos; triggers de imutabilidade preservados.
Snapshots globais anteriores continuam intactos para compatibilidade/auditoria.
check_inventory confere diferença de quantidade/valor contra cada movimento
que possui snapshot empresarial. Variância continua separada: snapshot de
valor usa valor efetivamente incorporado ao estoque, não custo com variância.

Testes de entrada/transferência/estorno e migração com comparação campo a campo.
Não habilita proprietário secundário nem substitui os testes A/B/C ainda pendentes.
