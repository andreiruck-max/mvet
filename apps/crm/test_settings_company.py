from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone
from apps.core.models import Company
from .models import IntakeSettings, RecurrenceRule


class SettingsCompanyMigrationTests(TransactionTestCase):
    def test_empty_installation_gets_primary_without_changing_crm_settings(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('crm', '0005_crm_company_identity'),
                  ('core', '0014_remove_company_single_company_company_active_and_more')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            state.get_model('core', 'Company').objects.filter(pk=1).delete()
            self.assertFalse(state.get_model('core', 'Company').objects.filter(pk=1).exists())
            state.get_model('crm', 'IntakeSettings').objects.get_or_create(pk=1, defaults={'starts_on':timezone.localdate(), 'daily_limit':17})
            state.get_model('crm', 'RecurrenceRule').objects.get_or_create(result='OPT_OUT', defaults={'days':19})
            originals = {}
            for name in ['IntakeSettings', 'RecurrenceRule']:
                model = state.get_model('crm', name)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields, list(model.objects.order_by('pk').values(*fields)))
            MigrationExecutor(connection).migrate(latest)
            self.assertTrue(Company.objects.filter(pk=1).exists())
            Company.objects.get_or_create(pk=2, defaults={'active':False})
            for model in [IntakeSettings, RecurrenceRule]:
                fields, rows = originals[model.__name__]
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertEqual(set(model.objects.values_list('owning_company_id',flat=True)), {1})
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.update(owning_company_id=2)
        finally:
            MigrationExecutor(connection).migrate(latest)
