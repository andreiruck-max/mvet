from decimal import Decimal as D
from uuid import uuid4
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from apps.products.models import Product
from .models import StockMovement
from .services import reverse
from .tests import StockFixtures, DAY


class OwnerSnapshotTests(StockFixtures, TestCase):
    def test_receipt_transfer_and_reversal_capture_owner_position(self):
        opening=self.op()
        first=opening.movements.get()
        self.assertEqual((first.owner_before_quantity,first.owner_after_quantity,
            first.owner_before_value,first.owner_after_value),(D('0'),D('10'),D('0'),D('50')))
        transfer=self.op('TRANSFER',quantity=D('2'),target_location_id=self.full.pk)
        legs=list(transfer.movements.order_by('pk'))
        self.assertEqual((legs[0].owner_before_quantity,legs[0].owner_after_quantity),(D('10'),D('8')))
        self.assertEqual((legs[1].owner_before_quantity,legs[1].owner_after_quantity),(D('8'),D('10')))
        reverse(actor=self.actor,operation_id=transfer.pk,key=uuid4(),date=DAY,reason='Reverter teste')
        for movement in StockMovement.objects.all():
            self.assertEqual(movement.owner_after_quantity-movement.owner_before_quantity,movement.quantity)
            self.assertEqual(movement.owner_after_value-movement.owner_before_value,movement.value)
        call_command('check_inventory')


class OwnerSnapshotMigrationTests(StockFixtures, TransactionTestCase):
    def test_legacy_ledger_is_not_rewritten_or_given_invented_snapshot(self):
        self.op()
        products=list(Product.objects.order_by('pk').values())
        executor=MigrationExecutor(connection)
        latest=executor.loader.graph.leaf_nodes()
        before=[('inventory','0012_stock_company_identity')]
        try:
            executor.migrate(before)
            state=executor.loader.project_state(before).apps
            Legacy=state.get_model('inventory','StockMovement')
            fields=[f.attname for f in Legacy._meta.concrete_fields]
            rows=list(Legacy.objects.order_by('pk').values(*fields))
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(list(StockMovement.objects.order_by('pk').values(*fields)),rows)
            for field in ('owner_before_quantity','owner_after_quantity','owner_before_value','owner_after_value'):
                self.assertFalse(StockMovement.objects.exclude(**{field:None}).exists())
            self.assertEqual(list(Product.objects.order_by('pk').values()),products)
            call_command('check_inventory')
        finally:
            MigrationExecutor(connection).migrate(latest)
