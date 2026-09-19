# MVet 1.0
ERP gerencial interno da Mercadovet Produtos Agroveterinários.

## Estado atual
**Fundação, estoque, vendas, compras, financeiro, despesas, relatórios e notificações implementados.** A Fase 7 adiciona [dashboard próximo das planilhas](docs/DASHBOARD.md), vendas tabulares, caixa organizado por dia, compras a pagar e [DRE gerencial](docs/DRE.md). [PR #16](https://github.com/andreiruck-max/mvet/pull/16): 206 testes PostgreSQL e 6 Chromium aprovados. A Fase 8 inclui a [central de notificações](docs/NOTIFICATIONS.md), preferências por usuário e monitoramento de backup. [PR #17](https://github.com/andreiruck-max/mvet/pull/17): 219 testes PostgreSQL e 7 Chromium aprovados. Depreciação/amortização, classificação de abatimentos e fechamento contábil não estão implementados; pendências ficam explícitas no resultado.

**Entrada manual; corte em 15/09/2026**, America/Sao_Paulo. A planilha é referência funcional, sem migração integral. Aberturas não afetam a DRE. Sem emissão fiscal e sem substituição do Bling.

## Stack
Python 3.12, Django 5.2.17 LTS, PostgreSQL 16, Django ORM, templates e CSS/JS locais, Gunicorn, WhiteNoise e Docker Compose. Sem CDN obrigatório. Versões Python fixadas em requirements.txt.

## Instalação com Docker
Requisitos: Git, Docker Engine/Desktop com Compose e terminal na pasta do projeto.
1. Clone o repositório e entre na pasta:
   `git clone https://github.com/andreiruck-max/mvet.git`
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

`setup_mvet` é idempotente e preserva personalizações de perfis existentes. Não cria usuários/senhas padrão. Configure usuários e permissões em **Usuários e acessos**. Apenas superusuário administra identidades e permissões; o grupo ADMINISTRADOR é um perfil operacional, não concede superusuário.

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
- [Estoque](docs/INVENTORY.md), [vendas](docs/SALES.md), [compras](docs/PURCHASES.md), [financeiro](docs/FINANCE.md), [DRE](docs/DRE.md).
- [Permissões](docs/PERMISSIONS.md), [API](docs/API.md), [importações](docs/IMPORTS.md), [testes](docs/TESTING.md).
- [Instalação](docs/DEPLOYMENT.md), [backup/restauração](docs/BACKUP_RESTORE.md), [manutenção por IA](docs/AI_MAINTENANCE.md), [ADRs](docs/adr/).
- [AGENTS](AGENTS.md), [CHANGELOG](CHANGELOG.md).

## Backup e segurança
Banco sem porta publicada no Compose padrão. Aplicação ligada apenas em 127.0.0.1 por padrão. Para rede interna, seguir DEPLOYMENT e ajustar hosts/CSRF/firewall; não expor banco à internet.
`bash scripts/backup.sh` cria dump e valida seu catálogo; `bash scripts/test_restore.sh caminho.dump` testa em banco temporário isolado. Cópia externa e agendamento dependem da máquina da empresa; não estão automaticamente ativados.
Nunca versionar `.env`, planilhas comerciais, banco ou backups.

## Fase 2 — Produtos e estoque
Após aplicar migrations, acesse **Produtos e estoque**. Cadastre locais e produtos e use **Movimentar estoque**. As permissões da operação estão em [docs/PERMISSIONS.md](docs/PERMISSIONS.md).

A abertura pode usar somente o estoque da planilha, sem importar vendas, compras ou caixa. Execute primeiro a validação sem `--commit`, conforme [docs/INVENTORY.md](docs/INVENTORY.md). Nunca copie a planilha ou banco para o Git. A carga de desenvolvimento não representa instalação na máquina da empresa.

`python manage.py check_inventory` confere o saldo por produto/local e a valorização contra o livro de movimentos. Cópia de segurança e instalação continuam conforme os guias existentes.

## Vendas manuais
Fase 3: acesse **Vendas**, cadastre canais/regras tributárias e use **Nova venda**. Salvar gera rascunho; confirmar baixa estoque; cancelar repõe com rastreabilidade. A data física é a confirmação e o custo é snapshot do momento. Consulte [regras e operação](docs/SALES.md). Recebimentos e fluxo diário estão no financeiro; liquidações ativas exigem estorno antes de cancelar a venda.

Adaptações: Estoque Mercadovet como padrão físico configurável, Full e outros estoques selecionáveis na venda; alíquotas com data de início e recálculo retroativo auditado; taxas extras nome/valor como MDR. Uma instalação vazia recebe os dois estoques iniciais no setup, editáveis. Saldos existentes não são redistribuídos automaticamente.

## Compras e transferências
Acesse **Compras**: cadastre fornecedor, produtos e parcelas; confirme o compromisso e depois o recebimento. Frete/desconto/custos são rateados e o estoque de destino atualizado. Para transferir Mercadovet → Full ou entre outros locais, use **Movimentações → Transferência**. Consulte [regras de compras](docs/PURCHASES.md). Abra a parcela para marcar como paga no financeiro.

## Financeiro
Cadastre contas e saldos iniciais em **Financeiro → Contas financeiras**. Compras/vendas confirmadas já geram títulos: não recadastre. Defina conta/vencimento previstos e registre a liquidação efetiva. Transferências entre bancos são separadas das transferências de estoque. Consulte [operação e limites](docs/FINANCE.md).

## Central de notificações
Alertas internos de estoque mínimo, margem, vencimentos e backup, com leitura e preferências por usuário. Acesse **Notificações** no menu. Processamento periódico: `python manage.py refresh_notifications`; ver [regras e operação](docs/NOTIFICATIONS.md). Agendamento, backup externo e restauração na empresa continuam pendentes.
# Acessos individuais, arquivos e Bling

O master administra permissões individuais em **Usuários e acessos**, separando faturamento, custos, margens, DRE, caixa e ações operacionais. Exportações Excel/PDF disponíveis nos relatórios atuais, com filtros e autorização própria. [Guia de permissões](docs/PERMISSIONS.md) · [Exportações](docs/EXPORTS.md) · [Avaliação da API Bling](docs/BLING_INTEGRATION.md).

A integração Bling ainda não está ativa. NF com SKU é viável para pré-preenchimento assistido; saldo bancário real não foi confirmado pela API. A documentação distingue consulta, conciliação e implantação.

## Importação assistida Bling

Fila em `/integracoes/bling/`, conexão exclusiva do master e revisão antes de confirmar qualquer venda. Custos e cancelamentos permanecem locais. Instalação, permissões e limites: [docs/BLING_SETUP.md](docs/BLING_SETUP.md). Credenciais e homologação da conta real são necessárias antes do uso operacional; integração financeira não faz parte desta entrega.

## Preparação da implantação

Siga o [roteiro de implantação e aceite](docs/INSTALLATION_CHECKLIST.md). `python manage.py check_installation --network` verifica configuração e banco sem escrever dados; verificações presenciais de rede, recuperação e permissões continuam necessárias.
