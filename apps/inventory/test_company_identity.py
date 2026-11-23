from decimal import Decimal
from uuid import uuid4
from django.core.management import call_command
from django.db import connection, transaction, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from apps.core.models import Company
from apps.products.models import Product
from .models import (StockBalance, StockOperation, StockMovement,
                     OpeningImport, InventoryReconciliation)
from .services import reverse, _apply
from .tests import StockFixtures, DAY


class StockCompanyMigrationTests(StockFixtures, TransactionTestCase):
    def test_existing_ledger_balances_and_imports_survive(self):
        self.op('OPENING')
        transfer = self.op('TRANSFER', quantity=Decimal('2'), target_location_id=self.full.pk)
        reverse(actor=self.actor, operation_id=transfer.pk, key=uuid4(), date=DAY,
                reason='Estorno sintético')
        # Preserve a negative-sale replenishment variance as well as ordinary entries.
        with transaction.atomic():
            sale = StockOperation.objects.create(kind='SALE_OUT', date=DAY,
                reason='Venda sintética', actor=self.actor, fingerprint='sale')
            _apply(sale, self.fresh(), self.loc, Decimal('-12'), Decimal('-60'))
        self.op(quantity=Decimal('3'), cost=Decimal('7'))
        self.assertTrue(StockMovement.objects.exclude(cost_variance=0).exists())
        OpeningImport.objects.create(digest='a'*64, actor=self.actor, report={'rows':1})
        InventoryReconciliation.objects.create(digest='b'*64, base_date=DAY,
            actor=self.actor, report={'synthetic':True})
        product_before = Product.objects.values().get(pk=self.p.pk)
        models = [StockBalance, StockOperation, StockMovement, OpeningImport, InventoryReconciliation]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('inventory', '0011_alter_inventoryreconciliation_base_date')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            originals = {}
            for current in models:
                model = state.get_model('inventory', current.__name__)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[current.__name__] = (fields,list(model.objects.order_by('pk').values(*fields)))
            MigrationExecutor(connection).migrate(latest)
            for model in models:
                fields, rows = originals[model.__name__]
                self.assertTrue(rows)
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)),rows)
                self.assertEqual(set(model.objects.values_list('company_id',flat=True)),{1})
            self.assertEqual(Product.objects.values().get(pk=self.p.pk),product_before)
            call_command('check_inventory')
            for model, field, value in [(StockOperation,'reason','changed'),
                                       (StockMovement,'value',Decimal('99')),
                                       (InventoryReconciliation,'report',{})]:
                with self.assertRaises(DatabaseError), transaction.atomic():
                    model.objects.update(**{field:value})
            Company.objects.get_or_create(pk=2, defaults={'name':'Agro sintética','active':False})
            # Mutable projections/import logs must also reject a secondary owner for now.
            for model in [StockBalance, OpeningImport]:
                with self.assertRaises(DatabaseError), transaction.atomic():
                    model.objects.update(company_id=2)
        finally:
            MigrationExecutor(connection).migrate(latest)
