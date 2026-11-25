# ADR 0091 — Estoque físico por depósito e proprietário

O depósito é físico e o catálogo é compartilhado. A consulta de Grupo usa
os saldos por (empresa, SKU, depósito) para apresentar quantidades lado a lado.
A soma é algébrica, uma única vez, e não usa a projeção global de Product nem
soma kits aos seus componentes. Não é o saldo comercial de um marketplace.
O custo é o custo médio histórico do próprio CNPJ no local; saldo ausente não
é confundido com custo de referência zero.

Apenas a rota de consulta aceita Grupo, somente por GET/HEAD. O master vê
todos os proprietários cadastrados, inclusive inativos: inativação não apaga
um saldo patrimonial. Empregados precisam de vínculo ativo, autorização de
Grupo e consulta de estoque em cada empresa ativa. A consulta de custos é uma
permissão adicional em cada coluna. O usuário com escopo parcial não recebe os
nomes, saldos ou custos das demais empresas e vê apenas um subtotal autorizado.
A visão individual e as restrições de escrita permanecem como antes.

Sem migration e sem uma nova projeção persistente. Remover a consulta não
altera qualquer registro. O pedido/NF, a dívida de origem interempresa, a DRE
com eliminações e a integração de estoques comerciais são entregas distintas.
