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
Estoque já coberto na Fase 2; ver validação abaixo.
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

Limites da entrega 0.1.0: não houve revisão visual interativa, build do Dockerfile nem teste de backup/restauração na máquina destino. A suite valida templates por HTTP, não substitui essas verificações.

## Fase 2 — cobertura implementada
- 55 testes locais de backend (fundação, estoque, HTTP, permissões e importação).
- 3 testes adicionais PostgreSQL: saídas concorrentes, envio idempotente concorrente e triggers contra alteração/exclusão do livro.
- 1 teste Chromium separado: busca por SKU, entrada pelo formulário, persistência de quantidade/valor e layout móvel sem transbordamento da página.
- O CI primeiro executa 58 testes de backend no PostgreSQL (o teste de navegador é ignorado nessa execução), depois executa o teste de navegador com MVET_BROWSER_TESTS=1.
- Capturas de desktop e celular são artefatos do CI com dados exclusivamente sintéticos.

```bash
pip install playwright==1.58.0
python -m playwright install --with-deps chromium
MVET_BROWSER_TESTS=1 python manage.py test apps.inventory.test_browser --verbosity 2
```

A base de desenvolvimento foi carregada separadamente e conferida com check_inventory. O arquivo real e o banco não fazem parte do repositório. O ambiente local usou SQLite apenas para desenvolvimento e carga de referência; as garantias de concorrência e triggers foram verificadas no PostgreSQL do CI. A instalação da empresa deve usar PostgreSQL.

### Resultado verificado em 16/09/2026
[CI 35041612447](https://github.com/andreiruck-max/mvet/actions/runs/35041612447), commit 915227b2f79778da6d4c93fbe0c07200a9f9f30d: 58 testes de backend PostgreSQL e 1 de navegador Chromium aprovados; check, migrations, setup e collectstatic aprovados. Capturas desktop e móvel revisadas. A alteração posterior atualiza a documentação e o texto/atalho da página inicial, sem mudar regras transacionais.

Limites mantidos: build Docker e backup/restauração na máquina da empresa ainda não executados. A carga real foi realizada somente em desenvolvimento, sem publicação de dados comerciais.

## Fase 3 — vendas
Testes de rascunho, fórmula de contribuição, impostos/vigência/override, custo histórico, múltiplos itens, kit alterado, insuficiência/rollback, cancelamento após compra, UUID/revisão, NF/série normalizadas, permissões HTML/API e CSRF. PostgreSQL adicional: concorrência pela última unidade, confirmação simultânea da mesma venda, triggers de snapshots. Chromium: nova venda com duas linhas, busca SKU, salvar, confirmar, revisar em desktop/mobile e cancelar, verificando saldo final. Capturas usam dados sintéticos; anexadas ao CI.

Evidência Fase 3: [execução 35083787171](https://github.com/andreiruck-max/mvet/actions/runs/35083787171) no commit 92faa22495c2deac24f425163dcda30de7b1afa3: 87 descobertos, 85 backend aprovados e 2 Chromium executados separadamente. Capturas desktop/mobile revisadas. Ajuste posterior do formulário mantém os mesmos testes obrigatórios antes do merge. A falha inicial de encerramento de conexões do teste foi corrigida com fechamento explícito nas threads.

Adaptações solicitadas: testes adicionais de estoque padrão e troca para Full, cancelamento no local original, taxa MDR, alíquota retroativa/hoje/futura, vigências sucessivas, preservação de overrides/canceladas, rollback da auditoria e proteção PostgreSQL de revisões/taxas extras. Teste Chromium cobre seleção de outro estoque, taxa extra e alteração de alíquota. Resultado final registrado no PR #12.

## Fase 4
Testes: separação compromisso/recebimento, rateio com resíduo, média por recebimento, local de estoque, documento duplicado, parcelas sem multiplicar compra, valores inválidos, gratuitos, kits proibidos na aquisição, UUID/revisão, cancelamento seguro, rollback, CMV histórico, fornecedores, permissões HTML/API, CSRF e filtros por mesma parcela.
PostgreSQL: dois recebimentos concorrentes da mesma compra e proteção dos históricos. Chromium: fornecedor, compra com dois produtos/rateio/duas parcelas, confirmação, recebimento, visual desktop/mobile e transferência Mercadovet → Full. Evidências no PR da fase.

### Resultado verificado da Fase 4
[CI 35152071410](https://github.com/andreiruck-max/mvet/actions/runs/35152071410), commit `1fa5da17a76f1f4b262a415c4ce23ff5ac2ef305`: 131 testes descobertos, 128 backend PostgreSQL aprovados e 3 testes Chromium executados separadamente, todos aprovados. Migrations, setup, collectstatic e verificações sem falhas. Capturas de compra em desktop e celular revisadas; transferência Mercadovet → Full confirmada no teste de interface. Commit posterior registra somente esta evidência e o estado da documentação. Instalação, Docker e restauração na máquina da empresa permanecem pendentes.
