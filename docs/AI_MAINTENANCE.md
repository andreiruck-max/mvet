# Manutenção por IA
Ler AGENTS.md, arquitetura, backlog e documentos do domínio antes de alterar. Diferenciar contratos futuros de implementação existente.

1. Inspecionar branch, histórico e instruções; não sobrescrever trabalho alheio.
2. Identificar serviços e constraints afetados.
3. Definir risco e testes pertinentes antes de modificar dados financeiros.
4. Implementar alteração pequena, migrations e autorização backend.
5. Validar PostgreSQL, migrations, CSRF e UI. Custo/concurrency não se valida apenas com mocks.
6. Atualizar docs/ADR/CHANGELOG e commit.
7. Informar resultado, testes efetivamente executados e limitações.

Não reclassificar margem como EBITDA, recalcular CMV antigo, remover histórico, criar tabelas mensais, publicar secrets ou transformar abertura em receita. Não apresentar telas de implantação como módulos completos.
Falha de ambiente não autoriza afirmar validação não executada. Usar GitHub como fonte de verdade e registrar o estado verificável.
