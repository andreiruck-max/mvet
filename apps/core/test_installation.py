import json
from io import StringIO
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import DatabaseError, connection
from django.test import TestCase, override_settings
from apps.core.models import Company, AuditLog
from apps.sales.models import SalesChannel

MODULE = 'apps.core.management.commands.check_installation'


@override_settings(DEBUG=False, ALLOWED_HOSTS=['mvet.internal'], SESSION_COOKIE_SECURE=True,
                   CSRF_COOKIE_SECURE=True, SECURE_SSL_REDIRECT=True)
class InstallationTests(TestCase):
    def setUp(self):
        call_command('setup_mvet', stdout=StringIO())
        get_user_model().objects.create_superuser('installation-master', password='test-only')
        SalesChannel.objects.create(name='Loja')

    def report(self, **kwargs):
        output = StringIO()
        try:
            call_command('check_installation', json=True, stdout=output, **kwargs)
            failed = False
        except CommandError:
            failed = True
        return json.loads(output.getvalue()), failed

    def test_read_only_report_and_real_database_vendor(self):
        before = (Company.objects.count(), AuditLog.objects.count(), get_user_model().objects.count())
        result, failed = self.report(network=True)
        self.assertEqual(failed, connection.vendor != 'postgresql')
        self.assertEqual(result['automated_checks_passed'], not failed)
        self.assertEqual(before, (Company.objects.count(), AuditLog.objects.count(), get_user_model().objects.count()))
        self.assertTrue(result['manual_checks'])

    @override_settings(DEBUG=True, ALLOWED_HOSTS=['*'], SESSION_COOKIE_SECURE=False)
    def test_unsafe_network_configuration_fails(self):
        report, failed = self.report(network=True)
        self.assertTrue(failed)
        pending = {r['code'] for r in report['checks'] if r['status'] == 'PENDENTE'}
        self.assertTrue({'debug', 'hosts', 'https_settings'} <= pending)

    def test_connection_failure_never_exposes_driver_message(self):
        with patch(MODULE + '.connection.ensure_connection', side_effect=DatabaseError('password=PRIVATE')):
            result, failed = self.report()
        self.assertTrue(failed)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertIn('database_access', [r['code'] for r in result['checks']])

    def test_pending_migrations_skip_application_tables(self):
        executor = MagicMock()
        executor.migration_plan.return_value = [('pending', False)]
        with patch(MODULE + '.MigrationExecutor', return_value=executor), patch(MODULE + '.Company.objects.select_related') as query:
            result, failed = self.report()
        self.assertTrue(failed)
        query.assert_not_called()
        self.assertIn('migrations', [r['code'] for r in result['checks'] if r['status'] == 'PENDENTE'])

    def test_inactive_master_and_stock_are_reported(self):
        get_user_model().objects.update(is_active=False)
        Company.objects.update(default_stock_location=None)
        result, failed = self.report()
        self.assertTrue(failed)
        pending = {r['code'] for r in result['checks'] if r['status'] == 'PENDENTE'}
        self.assertTrue({'master', 'default_stock'} <= pending)
