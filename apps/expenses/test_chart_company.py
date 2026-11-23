from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from apps.core.models import Company
from .models import ChartOfAccount, ClassificationRule


class ChartCompanyMigrationTests(TransactionTestCase):
    def test_hierarchy_and_classification_survive(self):
        Company.objects.get_or_create(pk=1)
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('expenses', '0007_expense_company_identity')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            chart = state.get_model('expenses', 'ChartOfAccount')
            parent = chart.objects.create(code='TEST', name='Grupo sintético', nature='OPERATING', postable=False)
            child = chart.objects.create(code='TEST.01', name='Embalagem sintética', nature='OPERATING', parent=parent)
            state.get_model('expenses', 'ClassificationRule').objects.create(
                name='Regra sintética', field='description', operator='CONTAINS', value='embalagem', category=child)
            originals = {}
            for name in ['ChartOfAccount', 'ClassificationRule']:
                model = state.get_model('expenses', name)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields, list(model.objects.order_by('pk').values(*fields)))
            MigrationExecutor(connection).migrate(latest)
            Company.objects.get_or_create(pk=2, defaults={'active': False})
            for model in [ChartOfAccount, ClassificationRule]:
                fields, rows = originals[model.__name__]
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertEqual(set(model.objects.values_list('company_id', flat=True)), {1})
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.update(company_id=2)
        finally:
            MigrationExecutor(connection).migrate(latest)
