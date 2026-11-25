from django.db import IntegrityError, transaction
from django.test import TestCase
from apps.core.models import Company
from .tests import Fixture
from .models import Purchase


class PurchaseCompanyTests(Fixture, TestCase):
    def test_receipt_preserves_owner_and_amounts(self):
        purchase = self.received()
        self.assertEqual(purchase.company_id, 1)
        self.assertEqual(set(purchase.items.values_list('company_id', flat=True)), {1})
        self.assertEqual(set(purchase.installments.values_list('company_id', flat=True)), {1})
        self.assertEqual(purchase.total, 50)
        self.assertEqual(purchase.installments.get().financial_title.company_id, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)

    def test_existing_draft_cannot_be_reassigned_to_another_company(self):
        Company.objects.get_or_create(pk=2, defaults={'active': False})
        purchase = self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Purchase.objects.filter(pk=purchase.pk).update(company_id=2)
        purchase.refresh_from_db()
        self.assertEqual(purchase.company_id, 1)


from datetime import date
from decimal import Decimal
from django.contrib.auth.models import User
from django.db import connection, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from apps.products.models import Product
from apps.inventory.models import StockLocation


class PurchaseCompanyMigrationTests(TransactionTestCase):
    def test_confirmed_purchase_snapshots_and_guards_survive(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('purchases', '0007_purchase_account')]
        names = ['Purchase', 'PurchaseItem', 'PurchaseInstallment']
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            Company.objects.get_or_create(pk=1)
            user = User.objects.create(username='purchase-migration')
            product = Product.objects.create(sku='HISTORICAL', name='Historical item')
            location = StockLocation.objects.create(name='Historical warehouse')
            supplier = state.get_model('purchases', 'Supplier').objects.create(legal_name='Historical supplier')
            models = {name: state.get_model('purchases', name) for name in names}
            day = date(2026, 9, 15)
            purchase = models['Purchase'].objects.create(supplier=supplier, document='HISTORY',
                date=day, location_id=location.pk, created_by_id=user.pk, products_total=50, total=50)
            models['PurchaseItem'].objects.create(purchase=purchase, product_id=product.pk,
                quantity=10, unit_cost=5, subtotal=50, allocated_total=50, landed_unit_cost=5,
                sku_snapshot='HISTORICAL', name_snapshot='Historical item')
            models['PurchaseInstallment'].objects.create(purchase=purchase, number=1, due_date=day, amount=50)
            models['Purchase'].objects.filter(pk=purchase.pk).update(status='ORDERED')
            originals = {}
            for name, model in models.items():
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields, list(model.objects.order_by('pk').values(*fields)))
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgname LIKE 'protect_purchase%' ORDER BY oid")
                triggers = cursor.fetchall()
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            after = executor.loader.project_state(latest).apps
            for name, (fields, rows) in originals.items():
                model = after.get_model('purchases', name)
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertEqual(set(model.objects.values_list('company_id', flat=True)), {1})
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgname LIKE 'protect_purchase%' ORDER BY oid")
                self.assertEqual(cursor.fetchall(), triggers)
            with self.assertRaises(DatabaseError), transaction.atomic():
                after.get_model('purchases', 'PurchaseItem').objects.update(unit_cost=Decimal('6'))
        finally:
            MigrationExecutor(connection).migrate(latest)
