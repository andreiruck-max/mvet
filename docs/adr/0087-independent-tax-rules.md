# ADR 0087 — Regras e versões tributárias independentes por empresa

TaxRule e TaxRateChange admitem proprietários distintos, inclusive nomes iguais e
alíquotas diferentes. Cálculo, sugestão e histórico selecionam a própria empresa.
Migration 0021 remove somente bloqueios transitórios dessas duas tabelas; não
altera valores, IDs, vigências ou snapshots existentes.

Gatilhos PostgreSQL impedem trocar o proprietário de uma regra e inserir versão
cuja empresa difira da regra. Histórico tributário continua imutável. Acesso às
telas, ModelChoiceField e serviço de configuração primários filtram empresa.
Grupo não pode cadastrar/editar regras, nem por chamada direta ao serviço.

Agro continua inativa. Regras secundárias são exercitadas por fixtures internas;
configuração operacional secundária depende da etapa de autorização/telas do
módulo completo. Não liberar recálculo retroativo secundário por esta alteração.
Os demais documentos e revisões continuam sob as restrições transitórias atuais.

Testes verificam alíquotas 8% e 4% sobre a mesma base, revisão secundária para 12%
sem alterar a principal, rejeição de FK cruzada, rotas GET/POST e bloqueio de
transferência da regra no banco. A regressão de migration preserva o histórico.
Rollback exige ausência de regras secundárias; não excluir histórico para voltar.
