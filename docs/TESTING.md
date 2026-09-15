# Testes
Executar contra PostgreSQL:
```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py setup_mvet
python manage.py collectstatic --noinput
python manage.py test --verbosity 2
```

## Suite da fundação
20 testes: autenticação; permissões de operador/gerencial/financeiro; acesso direto por URL/API e POST; autorização no serviço; auditoria de configuração; corte não editável; Decimal/limites; singleton; setup idempotente; CSRF; logout por POST; usuário inativo; bloqueio de escalada pelo admin; auditoria imutável pelo admin; login e troca de senha auditados; headers e mensagens de setup.

## CI
.github/workflows/tests.yml usa PostgreSQL 16 e Python 3.12. Teste falho ou migration pendente bloqueia aceite. Status real deve ser conferido no GitHub Actions, não inferido da existência do workflow.

## Fases futuras
Estoque: entrada/média/saída/insuficiência/transferência/fracionamento/kit/reversão e concorrência com TransactionTestCase e conexões separadas.
Vendas: snapshot histórico, múltiplos itens, margem/impostos e cancelamento.
Financeiro: idempotência, saldos retroativos/futuros, transferência, abertura e competência.
Importação: duplicidade/preview/rollback quando implementada.
UI: testar desktop/móvel, contraste claro/escuro, foco por teclado, mensagens e submissão. Não confundir renderização de template em teste HTTP com revisão visual humana.

## Execução verificada
Em 15/09/2026, [execução PostgreSQL 35010742097](https://github.com/andreiruck-max/mvet/actions/runs/35010742097) concluiu com sucesso para o código do commit c588366faa913f97bf6491ed5311b8b01145eb09:
- 20 testes aprovados.
- System check sem erros.
- Nenhuma migration pendente de geração.
- Migrations, setup e collectstatic executados com sucesso.

Limites: não houve revisão visual interativa, build do Dockerfile nem teste de backup/restauração na máquina destino. A suite valida templates por HTTP, não substitui essas verificações.
