"""Read-only installation triage; never certifies network or backup readiness."""
import json
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from apps.core.models import Company
from apps.sales.models import SalesChannel


class Command(BaseCommand):
    help = 'Verifica configuração e banco sem alterar dados ou revelar credenciais.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--network', action='store_true', help='Exige configuração HTTPS para uso compartilhado.')
        parser.add_argument('--json', action='store_true', help='Saída estruturada, sem credenciais.')

    def handle(self, *args, **options):
        rows = []

        def add(code, ok, message):
            rows.append({'code': code, 'status': 'OK' if ok else 'PENDENTE', 'message': message})

        add('debug', not settings.DEBUG, 'Operação exige DJANGO_DEBUG=0.')
        add('hosts', bool(settings.ALLOWED_HOSTS) and all(
            h.strip() and '*' not in h for h in settings.ALLOWED_HOSTS),
            'Configure nomes/IPs explícitos em DJANGO_ALLOWED_HOSTS.')
        if options['network']:
            add('https_settings', settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
                and settings.SECURE_SSL_REDIRECT,
                'Configure e valide HTTPS antes de ativar cookies seguros e redirecionamento.')
        add('postgresql', connection.vendor == 'postgresql', 'A instalação operacional exige PostgreSQL.')
        try:
            connection.ensure_connection()
            add('database', True, 'Conexão com o banco disponível.')
            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
            add('migrations', not pending, 'Aplique migrations antes de liberar a operação.')
            if not pending:
                company = Company.objects.select_related('default_stock_location').filter(pk=1).first()
                add('company', company is not None, 'Execute setup_mvet para inicializar a empresa.')
                add('master', get_user_model().objects.filter(is_active=True, is_superuser=True).exists(),
                    'Crie um master individual com createsuperuser.')
                add('default_stock', bool(company and company.default_stock_location
                    and company.default_stock_location.active), 'Selecione um estoque padrão ativo nas configurações.')
                add('sales_channel', SalesChannel.objects.filter(active=True).exists(),
                    'Cadastre pelo menos um canal ativo para confirmar vendas.')
        except DatabaseError:
            # Driver messages may contain hosts, users or credentials. Never echo them.
            add('database_access', False, 'Falha de acesso ao banco. Confira serviço, configuração e permissões localmente.')
        except Exception:
            add('schema', False, 'Não foi possível verificar o schema. Revise o histórico de migrations localmente.')

        manual = [
            'Validar acesso HTTPS e certificado em outro computador da rede, firewall e reinicialização do servidor.',
            'Testar permissões com usuário operacional, inclusive URLs diretas e exportações Excel/PDF.',
            'Executar backup, restauração isolada e verificar cópia externa e agendamento.',
            'Conferir estoque de abertura, contas e saldos com a empresa antes do uso real.',
            'Se utilizar Bling, configurar OAuth e homologar notas reais na fila de conferência.',
        ]
        failed = any(row['status'] != 'OK' for row in rows)
        result = {'automated_checks_passed': not failed, 'checks': rows, 'manual_checks': manual,
                  'scope': 'Checagem local de configuração; não certifica implantação, HTTPS, backup ou Bling.'}
        if options['json']:
            self.stdout.write(json.dumps(result, ensure_ascii=False))
        else:
            for row in rows:
                self.stdout.write(f"{row['status']} [{row['code']}] {row['message']}")
            self.stdout.write('\nVerificações presenciais pendentes:')
            for item in manual:
                self.stdout.write(f'- {item}')
            self.stdout.write(result['scope'])
        if failed:
            raise CommandError('Instalação com pendências nas verificações automáticas.')
