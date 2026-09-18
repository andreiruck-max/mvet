# Instalação e desenvolvimento
## Docker local
Siga README. Banco PostgreSQL 16 sem porta publicada; web por padrão em 127.0.0.1:8000. Volumes persistem reinicializações. Não usar docker compose down -v em operação: remove o volume.

Atualização: backup testado → obter versão → docker compose build → migrate em janela de manutenção → subir web → testar login/operação. Migrations não são executadas automaticamente a cada worker.

## VS Code
Python 3.12. Criar ambiente virtual e instalar requirements.txt. Copiar .env.example e preencher secrets. Para banco de desenvolvimento isolado:
```sh
docker compose -f docker-compose.yml -f compose.dev.yml up -d db
python -m venv .venv
```
Ativar ambiente (Windows PowerShell: .venv\\Scripts\\Activate.ps1), pip install -r requirements.txt.
No .env local de desenvolvimento: POSTGRES_HOST=127.0.0.1 e DJANGO_DEBUG=1. O debugger VS Code carrega esse arquivo. Para comandos no terminal, exportar variáveis ou utilizar o script Python abaixo:
```powershell
# Carrega apenas pares simples da configuração local, sem executar o conteúdo.
Get-Content .env | Where-Object { $_ -match '^[A-Z_][A-Z0-9_]*=' } | ForEach-Object {
  $pair = $_ -split '=', 2
  [Environment]::SetEnvironmentVariable($pair[0], $pair[1], 'Process')
}
python manage.py migrate
python manage.py setup_mvet
python manage.py createsuperuser
python manage.py runserver
```
Comandos Django não leem .env automaticamente fora do Compose/debugger.
Crie/revise migrations localmente. CI exige que nenhuma migration esteja faltando.

## Rede interna
Cada pessoa usa credencial própria. O superusuário master cria contas e revisa **Usuários e acessos**; começar sem margens, DRE, custos, auditoria e bancos para funcionários que precisam só de faturamento. Esta versão adiciona migrations de AccessPolicy/permissões e troca o backend de autenticação: aplicar migrations, reiniciar aplicação e entrar novamente nas sessões antigas. Instalar requirements.txt atualizado para geração de PDF. Exportações funcionam no servidor sem Microsoft Excel.
Ajustar MVET_BIND para IP da interface interna, ALLOWED_HOSTS e CSRF_TRUSTED_ORIGINS para o endereço utilizado. Firewall limitado à rede da empresa. PostgreSQL permanece sem exposição.
Uso compartilhado deve adotar HTTPS por proxy confiável e então DJANGO_SECURE_COOKIES=1, DJANGO_SSL_REDIRECT=1. Não ativar SSL_REDIRECT antes de configurar HTTPS. Não confiar em headers de proxy de origem pública indiscriminadamente.
DEBUG=0 em operação. Secrets aleatórios separados. Conta de aplicação sem superusuário PostgreSQL em instalação endurecida; conta de migração com privilégios de DDL apenas durante atualização. Compose inicial usa o usuário criado pela imagem e deve ser endurecido antes de exposição além da máquina local.

## Validação
check, migrations, setup, collectstatic e testes PostgreSQL no CI. Testar backup/restauração na máquina destino. Nenhuma instalação na rede da empresa foi executada por esta entrega.

## Agendamento de notificações
Após migrations, executar `docker compose exec -T web python manage.py refresh_notifications`. Configurar repetição a cada 15 minutos no agendador do servidor, com diretório do projeto e registro de saída/erros. Habilitar monitoramento de backup somente ao implantar a rotina. O repositório fornece comandos; não instala agendamentos na máquina da empresa.
