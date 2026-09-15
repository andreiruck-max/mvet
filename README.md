# MVet 1.0
ERP gerencial interno da Mercadovet Produtos Agroveterinários.

## Estado atual
**Fundação implementada:** autenticação, papéis/permissões, configuração da empresa, auditoria, layout claro/escuro, Docker e testes PostgreSQL. O CI valida cada alteração. Os módulos de produtos, estoque, vendas, compras e financeiro ainda estão planejados. Esta entrega não é um ERP pronto para operar.

**Entrada manual; corte em 15/09/2026**, America/Sao_Paulo. A planilha é referência funcional, sem migração integral. Aberturas não afetam a DRE. Sem emissão fiscal e sem substituição do Bling.

## Stack
Python 3.12, Django 5.2.17 LTS, PostgreSQL 16, Django ORM, templates e CSS/JS locais, Gunicorn, WhiteNoise e Docker Compose. Sem CDN obrigatório. Versões Python fixadas em requirements.txt.

## Instalação com Docker
Requisitos: Git, Docker Engine/Desktop com Compose e terminal na pasta do projeto.
1. Clone o repositório e entre na pasta.
2. Copie `.env.example` para `.env` (PowerShell: `Copy-Item .env.example .env`).
3. Gere dois valores aleatórios com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Use um em DJANGO_SECRET_KEY e outro em POSTGRES_PASSWORD. Não mantenha os placeholders.
4. Execute:
```sh
docker compose build
docker compose up -d db
docker compose run --rm web python manage.py migrate --noinput
docker compose run --rm web python manage.py setup_mvet
docker compose run --rm web python manage.py createsuperuser
docker compose up -d web
```
5. Abra [localhost:8000](http://localhost:8000) e entre com o usuário criado.

`setup_mvet` é idempotente e preserva personalizações de perfis existentes. Não cria usuários/senhas padrão. Configure usuários e grupos no admin. Apenas superusuário administra identidades e permissões; o grupo ADMINISTRADOR é um perfil operacional, não concede superusuário.

## Principais comandos
```sh
docker compose exec web python manage.py check
docker compose exec web python manage.py test --verbosity 2
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py changepassword LOGIN
docker compose logs --tail=100 web
```

Após alterar models em desenvolvimento: `python manage.py makemigrations`, revisar/versionar migrations, executar `python manage.py migrate` e testes em PostgreSQL. Nunca corrigir schema manualmente.

## Desenvolvimento no VS Code
Consulte [DEPLOYMENT](docs/DEPLOYMENT.md). Use ambiente virtual Python 3.12 e PostgreSQL. O debugger lê `.env`. O Compose de desenvolvimento publica o banco apenas em 127.0.0.1.

## Documentação
- [Visão](docs/PRODUCT_VISION.md), [backlog](docs/BACKLOG.md), [arquitetura](docs/ARCHITECTURE.md), [modelo/ERD](docs/DATA_MODEL.md), [regras](docs/BUSINESS_RULES.md).
- [Estoque](docs/INVENTORY.md), [vendas](docs/SALES.md), [financeiro](docs/FINANCE.md), [DRE](docs/DRE.md).
- [Permissões](docs/PERMISSIONS.md), [API](docs/API.md), [importações](docs/IMPORTS.md), [testes](docs/TESTING.md).
- [Instalação](docs/DEPLOYMENT.md), [backup/restauração](docs/BACKUP_RESTORE.md), [manutenção por IA](docs/AI_MAINTENANCE.md), [ADRs](docs/adr/).
- [AGENTS](AGENTS.md), [CHANGELOG](CHANGELOG.md).

## Backup e segurança
Banco sem porta publicada no Compose padrão. Aplicação ligada apenas em 127.0.0.1 por padrão. Para rede interna, seguir DEPLOYMENT e ajustar hosts/CSRF/firewall; não expor banco à internet.
`bash scripts/backup.sh` cria dump e valida seu catálogo; `bash scripts/test_restore.sh caminho.dump` testa em banco temporário isolado. Cópia externa e agendamento dependem da máquina da empresa; não estão automaticamente ativados.
Nunca versionar `.env`, planilhas comerciais, banco ou backups.
