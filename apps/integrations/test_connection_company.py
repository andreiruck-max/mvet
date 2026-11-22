from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from apps.core.models import Company
from .models import BlingConnection


class ConnectionCompanyMigrationTests(TransactionTestCase):
    def test_existing_connection_identity_and_ciphertext_preserved(self):
        Company.objects.get_or_create(pk=1)
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('integrations', '0012_blingbankaccount_blingbanklink_blingbankentry_and_more')]
        try:
            executor.migrate(before)
            model = executor.loader.project_state(before).apps.get_model('integrations', 'BlingConnection')
            model.objects.create(pk=1, issuer='12345678000195', tokens='synthetic-ciphertext-not-a-secret')
            fields = [f.attname for f in model._meta.concrete_fields]
            rows = list(model.objects.values(*fields))
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(list(BlingConnection.objects.values(*fields)), rows)
            self.assertEqual(BlingConnection.objects.get(pk=1).company_id, 1)
            Company.objects.get_or_create(pk=2, defaults={'active': False})
            with self.assertRaises(IntegrityError), transaction.atomic():
                BlingConnection.objects.filter(pk=1).update(company_id=2)
        finally:
            MigrationExecutor(connection).migrate(latest)
