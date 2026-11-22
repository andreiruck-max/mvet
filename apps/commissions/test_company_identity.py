from decimal import Decimal
from django.db import connection, transaction, DatabaseError, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from apps.core.models import Company
from apps.finance.models import FinancialEntry
from .tests import Fixture
from .models import CommissionPlan, Installment, Command, Entry, Payment, Allocation

MODELS = [CommissionPlan, Installment, Command, Entry, Payment, Allocation]


class CommissionCompanyTests(Fixture, TestCase):
    def test_release_payment_and_allocation_keep_owner_without_bank_effect(self):
        plan = self.plan()
        self.receipt(plan)
        self.payment('10')
        for model in MODELS:
            self.assertEqual(set(model.objects.values_list('company_id', flat=True)), {1})
        self.assertEqual(Payment.objects.get().amount, Decimal('10'))
        self.assertFalse(FinancialEntry.objects.exists())

    def test_secondary_plan_rejected(self):
        Company.objects.get_or_create(pk=2, defaults={'active': False})
        plan = self.plan()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CommissionPlan.objects.filter(pk=plan.pk).update(company_id=2)


class CommissionCompanyMigrationTests(Fixture, TransactionTestCase):
    def test_paid_commission_and_snapshots_survive(self):
        plan = self.plan()
        self.receipt(plan)
        self.payment('10')
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('commissions', '0005_commissionplan_basis_alter_payee_kind')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            originals = {}
            for current in MODELS:
                name = current.__name__
                model = state.get_model('commissions', name)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields, list(model.objects.order_by('pk').values(*fields)))
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgname LIKE 'commissions_%_immutable' ORDER BY oid")
                triggers = cursor.fetchall()
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            after = executor.loader.project_state(latest).apps
            for name, (fields, rows) in originals.items():
                model = after.get_model('commissions', name)
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertEqual(set(model.objects.values_list('company_id',flat=True)), {1})
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgname LIKE 'commissions_%_immutable' ORDER BY oid")
                self.assertEqual(cursor.fetchall(), triggers)
            with self.assertRaises(DatabaseError), transaction.atomic():
                Payment.objects.update(amount=Decimal('999'))
            self.assertFalse(FinancialEntry.objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
