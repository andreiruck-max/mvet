from decimal import Decimal as D
from uuid import uuid4
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.management import call_command
from apps.sales.tests import Fixture
from apps.sales.services import confirm, cancel
from apps.products.models import Product
from apps.accounts.models import AccessPolicy
from apps.reporting.datasets import build
from .models import StockLocation, StockBalance
from .services import execute, reverse as reverse_stock
from .selectors import catalog, stock_totals


class Mvet15Tests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.full = StockLocation.objects.create(name='Full Mercado Livre')
        self.company.default_stock_location = self.location
        self.company.save()
        self.product.sku = '31'; self.product.save(update_fields=['sku'])
        self.op('RECEIPT', self.full, D(4), D(20))
        self.client.force_login(self.actor)

    def op(self, kind, location, quantity, cost=None, **kwargs):
        return execute(actor=self.actor, key=uuid4(), kind=kind, date=timezone.localdate(), reason='Teste MVet 1.5', product_id=self.product.pk, location_id=location.pk, quantity=quantity, cost=cost, **kwargs)

    def balance(self, loc):
        return StockBalance.objects.get(product=self.product, location=loc)

    def test_sale_uses_selected_depot_and_cancel_preserves_snapshot(self):
        sale = self.draft(location=self.full)
        sale = confirm(actor=self.operator, sale_id=sale.pk, revision=sale.revision)
        self.assertEqual(sale.cmv, 40)
        self.assertEqual(sale.items.get().unit_cost, 20)
        self.assertEqual(self.balance(self.location).quantity, 10)
        self.assertEqual(self.balance(self.full).quantity, 2)
        self.op('RECEIPT', self.full, D(2), D(30))
        cancel(actor=self.actor, sale_id=sale.pk, reason='Teste cancelamento')
        sale.refresh_from_db()
        self.assertEqual(sale.cmv, 40)
        self.assertEqual(self.balance(self.full).value, 140)
        local_sale = self.confirmed(invoice_number='101')
        self.assertEqual(local_sale.cmv, 10)
        call_command('check_inventory')

    def test_transfer_carries_source_cost_and_reversal_restores_each_cost(self):
        operation = self.op('TRANSFER', self.location, D(2), target_location_id=self.full.pk)
        self.assertEqual(self.balance(self.location).value, 40)
        self.assertEqual(self.balance(self.full).value, 90)
        self.assertEqual(self.balance(self.full).average_cost, 15)
        reverse_stock(actor=self.actor, operation_id=operation.pk, key=uuid4(), date=timezone.localdate(), reason='Teste estorno')
        self.assertEqual(self.balance(self.full).average_cost, 20)
        self.assertEqual(self.balance(self.location).average_cost, 5)
        call_command('check_inventory')

    def test_revalue_is_local_and_full_depletion_clears_local_value(self):
        self.op('REVALUE', self.full, D(0), D(25))
        self.assertEqual(self.balance(self.location).value, 50)
        self.op('ISSUE', self.full, D(4))
        self.assertEqual(self.balance(self.full).value, 0)
        self.assertEqual(self.balance(self.location).value, 50)
        with self.assertRaises(ValidationError): self.op('ISSUE', self.full, D(1))
        call_command('check_inventory')

    def test_list_and_export_use_local_quantity_cost_and_fixed_totals(self):
        totals = None
        for location, quantity, cost, value in [(self.location, 10, 5, 50), (self.full, 4, 20, 80)]:
            response = self.client.get(reverse('products'), {'location': location.pk, 'q': '31'})
            self.assertEqual(response.status_code, 200)
            row = list(response.context['page'])[0]
            self.assertEqual((row.stock_quantity, row.stock_cost, row.stock_value), (quantity, cost, value))
            current = response.context['stock_totals']
            if totals is not None: self.assertEqual(totals, current)
            totals = current
            self.assertEqual(response.context['stock_total'], 130)
            dataset = build('stock', self.actor, {'location': str(location.pk), 'q': '31'})
            self.assertEqual(dataset.rows[0][2:5], [D(quantity), D(cost), D(value)])
        self.assertEqual(self.client.get(reverse('products')).context['location'], self.location)
        self.assertEqual(self.client.get(reverse('products'), {'location': 'bad'}).status_code, 400)

    def test_exact_sku_numeric_order_and_fifty_per_page(self):
        for sku in ['2', '101', '1000', '1009', '1031', '1131', '331', 'A31', '9'*60]:
            Product.objects.create(sku=sku, name='Produto '+sku)
        expected = ['2', '31', '101', '331', '1000', '1009', '1031', '1131', '9'*60, 'A31']
        self.assertEqual(list(catalog({}).values_list('sku', flat=True)), expected)
        self.assertEqual(list(catalog({'q': '31'}).values_list('sku', flat=True)), ['31'])
        self.assertEqual(catalog({'q': '99'}).count(), 0)
        self.assertEqual(len(self.client.get(reverse('product_lookup'), {'q': '31'}).json()['results']), 1)
        Product.objects.bulk_create([Product(sku='X'+str(i),name='Extra '+str(i)) for i in range(51)])
        page = self.client.get(reverse('products'), {'location': self.full.pk}).context['page']
        self.assertEqual(len(page), 50)
        self.assertEqual(page.paginator.count, 61)

    def test_lookup_and_permission(self):
        result = self.client.get(reverse('product_lookup'), {'q':'31', 'location':self.full.pk}).json()['results'][0]
        self.assertEqual(D(result['cost']), 20)
        AccessPolicy.objects.update_or_create(user=self.operator, defaults={'rules':{'core.view_stock':True,'core.view_costs':False}})
        self.client.force_login(self.operator)
        response = self.client.get(reverse('products'))
        self.assertNotContains(response, 'R$')
        self.assertNotIn('stock_totals', response.context)
        self.assertNotIn('cost', self.client.get(reverse('product_lookup'), {'q':'31', 'location':self.full.pk}).json()['results'][0])

    def test_existing_ledger_recovers_distinct_local_values_without_changing_history(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        migration = import_module('apps.inventory.migrations.0006_stockbalance_average_cost_stockbalance_value_and_more')
        before = list(self.product.movements.values())
        StockBalance.objects.filter(product=self.product).update(value=0, average_cost=0)
        from types import SimpleNamespace
        editor = SimpleNamespace(connection=connection, execute=lambda sql: connection.cursor().execute(sql))
        migration.populate_local_costs(apps, editor)
        self.assertEqual(self.balance(self.location).value, 50)
        self.assertEqual(self.balance(self.full).value, 80)
        self.assertEqual(self.balance(self.full).average_cost, 20)
        self.assertEqual(list(self.product.movements.values()), before)
        StockBalance.objects.filter(product=self.product, location=self.full).update(quantity=99)
        with self.assertRaises(RuntimeError): migration.populate_local_costs(apps, editor)

    def test_kit_and_fraction_consume_source_depot_cost(self):
        from apps.products.services import set_components
        kit = Product.objects.create(sku='KIT-LOCAL', name='Kit teste', kind='KIT')
        set_components(actor=self.actor, kit_id=kit.pk, items=[(self.product.pk, D(2))])
        sale = self.draft(items=[(kit.pk, D(1))], location=self.full)
        sale = confirm(actor=self.operator, sale_id=sale.pk, revision=sale.revision)
        self.assertEqual(sale.cmv, 40)
        target = Product.objects.create(sku='FRAC-LOCAL', name='Fracionado')
        self.op('SPLIT', self.full, D(1), target_product_id=target.pk, target_quantity=D(10), target_location_id=self.location.pk)
        self.assertEqual(StockBalance.objects.get(product=target, location=self.location).average_cost, 2)
        self.assertEqual(self.balance(self.location).average_cost, 5)
        call_command('check_inventory')
