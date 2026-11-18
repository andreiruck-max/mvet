# MVet 3.0 — laboratório (PR 0)

Base: `develop/mvet-3.0`. Esta fase prepara infraestrutura, sem implementar
multiempresa e sem migrations novas. A base 51a8435 precede as últimas melhorias
2.0: antes da migração empresarial, reconciliar essas melhorias com regressão,
sem incorporar alterações silenciosamente nesta PR.

## Isolamento

Clone separado em `C:\Mercadovet\mvet3`, nunca na pasta operacional `mvet`.
Docker Desktop e Python 3.12 disponíveis. Não usar o atualizador 2.0 neste clone.
O Compose `compose.mvet3.yml` é independente, não um override do Compose 2.0.
Projeto `mvet3`, rede interna `mvet3_lab`, volume `mvet3_lab_pgdata`, banco/usuário
`mvet3_lab`, host `lab-db`, HTTP **127.0.0.1:8001**; PostgreSQL sem porta publicada.
Não há bind mount, `.env` operacional ou worker automático. Cookies de sessão e
CSRF têm nomes próprios para não derrubar a sessão do 2.0 no mesmo navegador.

`config.settings_mvet3` fixa identidade do banco, limpa credenciais Bling e
bloqueia transporte HTTP, OAuth e XML, inclusive com tokens em uma cópia do banco.
Rede Docker interna fornece segunda barreira contra saída externa. O build precisa
acessar os registros de imagens/dependências; isso ocorre antes da execução do app.
Não acrescentar uma segunda rede, não usar host networking ou credenciais reais.
O bloqueio não cria escopo empresarial: isso pertence às próximas PRs.

## Inicialização com dados sintéticos

Na pasta do clone 3.0, usando a branch desta PR ou develop após integração:

```powershell
python scripts/mvet3_lab.py init
python scripts/mvet3_lab.py build
python scripts/mvet3_lab.py start-db
python scripts/mvet3_lab.py audit
python scripts/mvet3_lab.py migrate
python scripts/mvet3_lab.py setup
python scripts/mvet3_lab.py check
python scripts/mvet3_lab.py restore-test
python scripts/mvet3_lab.py up
```

`init` gera segredos locais próprios em `.env.mvet3` e recusa sobrescrever o arquivo.
Nunca publicar esse arquivo; ele também fica fora do build Docker. `migrate` é
explícito e só usa o banco identificado como `mvet3_lab/mvet3_lab`. Não há migration
no start do web. `setup` cria apenas os cadastros legados no laboratório, não a MVet Agro.

Para criar login local:

```powershell
docker compose --project-name mvet3 --env-file .env.mvet3 --file compose.mvet3.yml run --rm lab-web python manage.py createsuperuser
```

Abrir http://127.0.0.1:8001. O Bling deve informar que está bloqueado.
`audit` mostra projeto, volume, containers e identidade SQL, sem senhas/tokens.
O script ignora variáveis `COMPOSE_*` e `MVET3_*` herdadas do terminal: utiliza o
arquivo de laboratório explicitamente.

## Restauração e retorno

`restore-test` cria um banco temporário com UUID no PostgreSQL do laboratório,
restaura um dump do próprio laboratório e compara contagens de empresa/migrations.
Remove apenas esse banco temporário ao terminar. Esse teste não comprova integridade
do backup real, saldos ou estoque: o checkpoint 2.0 continua separado. A homologação
com dados reais e baseline completo é etapa posterior; não carregar dumps de
produção nesta PR nem publicar dados, tokens ou arquivos comerciais.

Para parar: `python scripts/mvet3_lab.py stop`. Volume preservado. Não há comando
que remova volumes ou restaure sobre o banco ativo. Retornar à versão anterior do
código do laboratório não modifica o 2.0. Não implantar este ambiente em produção.

## Validação

Workflow `Tests`: regressão existente PostgreSQL 16, migrations, setup, arquivos
estáticos, Chromium e PowerShell. Workflow `MVet 3 laboratory`: build real Docker,
auditoria, migrations sintéticas, restauração isolada, HTTP porta 8001, bloqueio de
egress e login Chromium com cookie próprio. Testes de transporte em
`apps.integrations.test_lab_isolation` verificam bloqueio antes de rede/credenciais.
Resultados efetivos devem ser consultados na PR; configuração de CI não significa
que os testes passaram. Não há teste do Docker Desktop na máquina operacional.
