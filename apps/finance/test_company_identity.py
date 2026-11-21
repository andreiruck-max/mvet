from datetime import date
from decimal import Decimal

from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from apps.core.models import Company
from .models import FinancialAccount


class AccountCompanyTests(TestCase):
    def test_legacy_default_and_secondary_account_block(self):
        Company.objects.get_or_create(pk=1)
        Company.objects.get_or_create(pk=2, defaults={'active': False})
        account = FinancialAccount.objects.create(name='Primary bank', kind='BANK',
            opening_date=date(2026, 9, 15), opening_balance=Decimal('13000.00'))
        self.assertEqual(account.company_id, 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FinancialAccount.objects.filter(pk=account.pk).update(company_id=2)
        account.refresh_from_db()
        self.assertEqual(account.company_id, 1)
        self.assertEqual(account.opening_balance, Decimal('13000.00'))


class AccountCompanyMigrationTests(TransactionTestCase):
    def test_existing_account_fields_and_trigger_survive_additive_migration(self):
        before = [('finance', '0006_duepayment')]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            Company.objects.get_or_create(pk=1)
            Account = state.get_model('finance', 'FinancialAccount')
            account = Account.objects.create(name='Historical bank', kind='BANK',
                opening_date=date(2026, 9, 15), opening_balance=Decimal('12345.67'))
            fields = [f.attname for f in Account._meta.concrete_fields]
            original = Account.objects.values(*fields).get(pk=account.pk)
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid, tgenabled FROM pg_trigger WHERE tgname='finance_account_opening'")
                trigger = cursor.fetchone()
            self.assertIsNotNone(trigger)
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            restored = FinancialAccount.objects.values(*fields).get(pk=account.pk)
            self.assertEqual(restored, original)
            self.assertEqual(FinancialAccount.objects.get(pk=account.pk).company_id, 1)
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid, tgenabled FROM pg_trigger WHERE tgname='finance_account_opening'")
                self.assertEqual(cursor.fetchone(), trigger)
        finally:
            MigrationExecutor(connection).migrate(latest)
