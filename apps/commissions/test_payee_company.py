from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from apps.core.models import Company
from .tests import Fixture
from .models import Payee, CommissionSettings, CommissionPlan


class PayeeCompanyMigrationTests(Fixture, TransactionTestCase):
    def test_terms_and_existing_plan_preserved(self):
        plan = self.plan()
        CommissionSettings.objects.get_or_create(pk=1)
        snapshot = CommissionPlan.objects.values().get(pk=plan.pk)
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('commissions', '0006_commission_company_identity')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            originals = {}
            for name in ['Payee', 'CommissionSettings']:
                model = state.get_model('commissions', name)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields, list(model.objects.order_by('pk').values(*fields)))
            MigrationExecutor(connection).migrate(latest)
            Company.objects.get_or_create(pk=2, defaults={'active': False})
            for model in [Payee, CommissionSettings]:
                fields, rows = originals[model.__name__]
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertEqual(set(model.objects.values_list('company_id', flat=True)), {1})
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.update(company_id=2)
            self.assertEqual(CommissionPlan.objects.values().get(pk=plan.pk), snapshot)
        finally:
            MigrationExecutor(connection).migrate(latest)
