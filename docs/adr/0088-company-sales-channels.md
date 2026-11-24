# ADR 0088 — Canais comerciais por empresa

O nome do canal deixa de ser globalmente único: a chave é empresa/nome. A migration
0022 preserva IDs e vínculos históricos, removendo apenas a restrição transitória
company=1. O banco impede trocar proprietário e vincular comissionado de outra
empresa. Canais iguais nos dois CNPJs não representam o mesmo registro comercial.

Configuração primária, formulários, correções de vendas, relatórios e importação
em lote filtram company=1 durante a transição. O serviço de correção valida a
empresa do canal contra a venda. Agro continua inativa e sem operação pública;
esta preparação não autoriza importação, comissão ou venda secundária.

Testes cobrem nomes iguais entre empresas, duplicidade dentro da empresa, escolha
por ID e acesso direto às telas, troca de proprietário e FK de comissão cruzada.
Regressão preserva vendas e histórico. Rollback requer resolver nomes duplicados
entre empresas por procedimento aprovado; não excluir histórico para reverter.
