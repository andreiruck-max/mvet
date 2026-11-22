from decimal import Decimal
from django.db import IntegrityError, transaction
from django.test import TestCase
from apps.core.models import Company
from .tests import Fixture
from .models import Sale


class SaleCompanyTests(Fixture, TestCase):
    def test_confirmation_preserves_cmv_tax_and_consumption_owner(self):
        sale = self.confirmed()
        self.assertEqual(sale.company_id, 1)
        item = sale.items.get()
        self.assertEqual(item.company_id, 1)
        self.assertEqual(item.consumptions.get().company_id, 1)
        self.assertEqual(sale.cmv, 10)
        self.assertEqual(str(sale.tax_amount), '4.75')
        self.receive(self.product, Decimal('10'), Decimal('20'))
        sale.refresh_from_db()
        self.assertEqual(sale.cmv, 10)

    def test_secondary_draft_is_rejected(self):
        Company.objects.get_or_create(pk=2, defaults={'active': False})
        sale = self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sale.objects.filter(pk=sale.pk).update(company_id=2)


from django.db import connection, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SaleCompanyMigrationTests(Fixture, TransactionTestCase):
    def test_confirmed_sale_cmv_and_consumptions_survive_migration(self):
        sale = self.confirmed()
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('sales', '0017_sale_commission_installments')]
        names = ['Sale', 'SaleItem', 'SaleConsumption', 'SaleExtraCost']
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            originals = {}
            for name in names:
                model = state.get_model('sales', name)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields, list(model.objects.order_by('pk').values(*fields)))
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgrelid IN ('sales_sale'::regclass,'sales_saleitem'::regclass,'sales_saleconsumption'::regclass,'sales_saleextracost'::regclass) ORDER BY oid")
                triggers = cursor.fetchall()
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            after = executor.loader.project_state(latest).apps
            for name, (fields, rows) in originals.items():
                model = after.get_model('sales', name)
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertFalse(model.objects.exclude(company_id=1).exists())
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgrelid IN ('sales_sale'::regclass,'sales_saleitem'::regclass,'sales_saleconsumption'::regclass,'sales_saleextracost'::regclass) ORDER BY oid")
                self.assertEqual(cursor.fetchall(), triggers)
            self.assertEqual(after.get_model('sales', 'Sale').objects.get(pk=sale.pk).cmv, Decimal('10'))
            with self.assertRaises(DatabaseError), transaction.atomic():
                after.get_model('sales', 'SaleItem').objects.update(cmv=Decimal('999'))
        finally:
            MigrationExecutor(connection).migrate(latest)
