import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from apps.core.models import Company
from apps.products.models import Product
from .location_import import load_snapshot
from .models import StockBalance, StockMovement, StockOperation, OpeningImport
from .services import execute, reverse
from uuid import uuid4


class LocationImportTests(TestCase):
    def setUp(self):
        Company.objects.create(pk=1)
        self.actor = User.objects.create_superuser('import-test', password='testing-only')
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'snapshot.json'
        self.clock = patch('apps.inventory.services.timezone.localdate', return_value=date(2026, 9, 21))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.data = {'version': 1, 'date': '2026-09-21', 'products': [
            {'sku': 'A', 'name': 'Teste A', 'unit': 'UN', 'balances': [
                {'location': 'Loja', 'quantity': '10', 'cost': '2'},
                {'location': 'Full', 'quantity': '2', 'cost': '5'}]},
            {'sku': 'B', 'name': 'Teste B', 'unit': 'FR', 'balances': [
                {'location': 'Loja', 'quantity': '0', 'cost': '9', 'note': 'Saldo corrigido por orientação do responsável.'}]}]}

    def load(self, commit=True, actor=None):
        self.path.write_text(json.dumps(self.data), encoding='utf-8')
        return load_snapshot(actor=actor or self.actor, path=self.path, commit=commit)

    def test_preview_writes_nothing(self):
        result = self.load(False)
        self.assertEqual(result['products'], 2)
        self.assertEqual(D(result['locations']['Loja']['value']), 20)
        self.assertFalse(Product.objects.exists())
        self.assertFalse(StockOperation.objects.exists())

    def test_locations_weighted_cost_audit_and_repeat(self):
        self.load()
        product = Product.objects.get(sku='A')
        self.assertEqual(product.quantity, 12)
        self.assertEqual(product.value, 30)
        self.assertEqual(product.average_cost, D('2.5'))
        self.assertEqual(StockBalance.objects.get(product=product, location__name='Full').quantity, 2)
        self.assertEqual(StockOperation.objects.filter(kind='OPENING').count(), 2)
        self.assertEqual(StockMovement.objects.count(), 3)
        self.assertEqual(Product.objects.get(sku='B').average_cost, 9)
        self.assertIn('Saldo corrigido', Product.objects.get(sku='B').movements.get().operation.reason)
        self.data['products'].reverse()
        self.data['products'][1]['balances'].reverse()
        self.assertTrue(self.load()['already_loaded'])
        self.assertEqual(StockMovement.objects.count(), 3)

    def test_invalid_row_rolls_back_entire_load(self):
        self.data['products'][1]['balances'][0]['quantity'] = '-5'
        with self.assertRaises(ValidationError):
            self.load()
        self.assertFalse(Product.objects.exists())

    def test_existing_sku_blocks_preview_and_commit(self):
        Product.objects.create(sku='B', name='Existing')
        for commit in (False, True):
            with self.assertRaises(ValidationError):
                self.load(commit)
        self.assertEqual(Product.objects.count(), 1)
        self.assertFalse(OpeningImport.objects.exists())

    def test_permission_checked_in_service(self):
        user = User.objects.create_user('no-access')
        with self.assertRaises(PermissionDenied):
            self.load(actor=user)
        self.assertFalse(Product.objects.exists())

    def test_zero_location_does_not_replace_weighted_cost(self):
        self.data['products'][0]['balances'][1].update(quantity='0', cost='99')
        self.load()
        self.assertEqual(Product.objects.get(sku='A').average_cost, 2)

    def test_duplicate_location_and_sku_rejected(self):
        self.data['products'][0]['balances'].append(self.data['products'][0]['balances'][0].copy())
        with self.assertRaises(ValidationError):
            self.load()
        self.data['products'][0]['balances'].pop()
        self.data['products'].append(self.data['products'][0].copy())
        with self.assertRaises(ValidationError):
            self.load()

    def test_future_or_before_cutover_rejected(self):
        for day in ('2026-09-22', '2026-09-14'):
            self.data['date'] = day
            with self.assertRaises(ValidationError):
                self.load()

    def test_backdated_operations_blocked_and_reversal_supported(self):
        self.load()
        product = Product.objects.get(sku='A')
        location = product.balances.get(location__name='Loja').location
        with self.assertRaises(ValidationError):
            execute(actor=self.actor, key=uuid4(), kind='ISSUE', date=date(2026, 9, 20),
                    reason='Backdate', product_id=product.pk, location_id=location.pk, quantity=D('1'))
        operation = product.movements.first().operation
        reverse(actor=self.actor, operation_id=operation.pk, key=uuid4(), date=date(2026, 9, 21), reason='Reverter carga')
        product.refresh_from_db()
        self.assertEqual(product.quantity, 0)
        self.assertEqual(product.value, 0)
        self.assertTrue(self.load()['already_loaded'])
