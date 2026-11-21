# Verificação do histórico antes da atribuição empresarial

Preparação da PR 2. O comando `check_company_history` lê os modelos dos módulos de negócio em uma única transação PostgreSQL REPEATABLE READ e READ ONLY. Não executa migrations, UPDATE, chamadas Bling ou desativação de triggers.

No banco isolado/restaurado do laboratório, antes da migration:

```sh
python manage.py check_company_history --baseline /caminho/privado/antes.json
```

Após a migration, sem operações concorrentes entre as duas capturas:

```sh
python manage.py check_company_history --compare /caminho/privado/antes.json
```

O arquivo contém nomes de modelos/campos, contagens e SHA-256 das linhas ordenadas pelo ID. Não contém valores comerciais nem credenciais. Guarde localmente; não versione arquivos gerados. Arquivo existente não é sobrescrito. Falhas retornam código diferente de zero e identificam apenas os modelos divergentes.

A comparação usa os campos originais, permitindo adicionar colunas. Se `company_id` for adicionado, exige Mercadovet (1) para todas as linhas da tabela histórica. Ainda não se destina a um banco com operações de outras empresas. Novas tabelas não fazem parte do baseline anterior. Campos removidos/renomeados invalidam a comparação. Hashes não substituem testes de regras, relatório financeiro ou testes de migrations: permitem detectar alteração de qualquer campo original, inclusive quando somas e contagens permanecem iguais. Novos registros entre capturas também são divergências; use cópia isolada sem atividade.

Nenhuma migration empresarial é entregue nesta preparação. Empresas secundárias permanecem inativas.
