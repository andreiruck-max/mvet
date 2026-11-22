from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from apps.core.models import Company
from .tests import Fixture
from .models import Contact, Interaction, ContactEvent


class CRMCompanyTests(Fixture, TestCase):
    def test_client_farm_and_owner_are_distinct(self):
        contact = self.contact(company='Fazenda do cliente')
        self.record(contact)
        self.assertEqual(contact.company, 'Fazenda do cliente')
        for model in [Contact, Interaction, ContactEvent]:
            self.assertEqual(set(model.objects.values_list('owning_company_id',flat=True)), {1})
        Company.objects.get_or_create(pk=2, defaults={'active':False})
        with self.assertRaises(IntegrityError), transaction.atomic():
            Contact.objects.filter(pk=contact.pk).update(owning_company_id=2)


class CRMCompanyMigrationTests(Fixture, TransactionTestCase):
    def test_contact_history_survives(self):
        contact = self.contact(company='Fazenda histórica')
        self.record(contact)
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('crm','0004_seed_intake_and_protect_releases')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            originals = {}
            for name in ['Contact','Interaction','ContactEvent']:
                model = state.get_model('crm',name)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields,list(model.objects.order_by('pk').values(*fields)))
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            after = executor.loader.project_state(latest).apps
            for name,(fields,rows) in originals.items():
                model=after.get_model('crm',name)
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)),rows)
                self.assertEqual(set(model.objects.values_list('owning_company_id',flat=True)),{1})
        finally:
            MigrationExecutor(connection).migrate(latest)
