# ADR 0064 — Identidade empresarial das contas bancárias

Primeira atribuição transacional da PR 2, restrita a FinancialAccount. Campo company obrigatório, PROTECT, default constante 1 durante a transição. A migration adiciona a coluna via DDL: não atualiza valores históricos, não altera IDs e não desativa gatilhos. A propriedade permanece bloqueada em 1 por CheckConstraint até contextualizar serviços, títulos, operações e lançamentos. Isso também impede ligações entre contas de empresas diferentes enquanto a consulta financeira é legada.

A unicidade global do nome permanece nesta etapa. Sua substituição por empresa + nome ocorrerá junto com formulários/serviços por empresa. Não permite abrir contas MVet Agro ainda. Campo não editável e fora dos campos aceitos pelo serviço atual de cadastro.

Teste de migration parte da versão anterior, cria conta histórica, aplica a nova versão e compara todos os campos anteriores, empresa atribuída e identidade/estado do trigger de proteção da abertura. Teste de banco rejeita mudança de proprietário para empresa 2. Suíte integral PostgreSQL e navegador valida os fluxos existentes. O comando de baseline da PR 2a permite conferência adicional em cópia isolada sem atividade.

Não executar esta migration na produção MVet 2.0. A reversão técnica remove a coluna/constraint; nesta fase ela só contém a atribuição constante 1. Nenhum lançamento é refeito. Uma futura ativação de outras empresas mudará a política de rollback e exigirá plano próprio.
