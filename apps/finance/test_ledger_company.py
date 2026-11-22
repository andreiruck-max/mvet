from django.db import IntegrityError, transaction
from django.test import TestCase
from apps.core.models import Company
from .tests import Fixture
from .models import FinancialTitle, FinancialOperation, FinancialEntry


class LedgerCompanyTests(Fixture, TestCase):
    def test_settlement_keeps_owner_and_rejects_cross_company_title(self):
        Company.objects.get_or_create(pk=2, defaults={'active': False})
        title = self.title()
        self.settle(title)
        self.assertEqual(title.company_id, 1)
        self.assertEqual(set(FinancialOperation.objects.values_list('company_id', flat=True)), {1})
        self.assertEqual(set(FinancialEntry.objects.values_list('company_id', flat=True)), {1})
        with self.assertRaises(IntegrityError), transaction.atomic():
            FinancialTitle.objects.create(company_id=2, actor=self.admin, direction='PAY',
                description='Forbidden owner', date=self.today, due_date=self.today, amount=10)


from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from django.db import connection, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LedgerCompanyMigrationTests(TransactionTestCase):
    def test_paid_history_and_immutable_triggers_survive(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('finance', '0007_account_company_identity')]
        names = ['FinancialTitle', 'FinancialOperation', 'FinancialEntry',
                 'FinancialTitleRevision', 'DuePayment']
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            Company.objects.get_or_create(pk=1)
            user = User.objects.create(username='migration-owner')
            Account = state.get_model('finance', 'FinancialAccount')
            models = {name: state.get_model('finance', name) for name in names}
            day = date(2026, 9, 15)
            account = Account.objects.create(name='Historical', kind='BANK', opening_date=day)
            title = models['FinancialTitle'].objects.create(actor_id=user.pk, direction='PAY',
                description='Historical purchase', date=day, due_date=day, amount=Decimal('100'), account=account)
            with transaction.atomic():
                op = models['FinancialOperation'].objects.create(actor_id=user.pk, title=title,
                    kind='SETTLEMENT', status='POSTED', date=day, description='Partial payment',
                    principal=Decimal('40'), actual=Decimal('40'), fingerprint='historical')
                models['FinancialEntry'].objects.create(operation=op, account=account, amount=Decimal('-40'))
                models['FinancialTitle'].objects.filter(pk=title.pk).update(settled=Decimal('40'))
            models['FinancialTitleRevision'].objects.create(title=title, actor_id=user.pk,
                number=1, reason='Historical revision', before={'amount':'100'}, after={'amount':'100'})
            models['DuePayment'].objects.create(title=title, actor_id=user.pk, account=account, enabled=False)
            originals = {}
            for name, model in models.items():
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields, list(model.objects.order_by('pk').values(*fields)))
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgname LIKE 'finance_%' ORDER BY oid")
                triggers = cursor.fetchall()
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            after = executor.loader.project_state(latest).apps
            for name, (fields, rows) in originals.items():
                model = after.get_model('finance', name)
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertEqual(set(model.objects.values_list('company_id', flat=True)), {1})
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgname LIKE 'finance_%' ORDER BY oid")
                self.assertEqual(cursor.fetchall(), triggers)
            with self.assertRaises(DatabaseError), transaction.atomic():
                after.get_model('finance', 'FinancialEntry').objects.update(amount=Decimal('-41'))
        finally:
            MigrationExecutor(connection).migrate(latest)
