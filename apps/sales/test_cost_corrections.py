from decimal import Decimal as D
from uuid import uuid4
from unittest import skipUnless
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, transaction, DatabaseError
from django.test import TestCase
from django.urls import reverse
from apps.inventory.models import StockMovement
from apps.reporting.selectors import sales_summary, channel_summary
from apps.reporting.datasets import sales_dataset
from .tests import Fixture
from .models import Sale, SaleCostRevision
from .cost_corrections import correct_cost
from .services import cancel
from .recovery import recover_sale


class CostCorrectionTests(Fixture, TestCase):
    def args(self, sale, cost='1.50'):
        return dict(actor=self.actor, sale_id=sale.pk, revision=sale.revision, key=uuid4(),
                    reason='Custo da embalagem informado como unidade', costs={sale.items.get().pk: D(cost)})

    def test_cost_changes_all_results_but_preserves_stock_and_snapshots(self):
        sale = self.confirmed()
        old_contribution = sale.contribution
        moves = list(StockMovement.objects.values())
        item = sale.items.get()
        self.product.refresh_from_db()
        stock = (self.product.quantity, self.product.value)
        result = correct_cost(**self.args(sale))
        self.assertEqual(result.cmv, D(10))
        self.assertEqual(result.effective_cmv, D(3))
        self.assertEqual(result.contribution, old_contribution + D(7))
        self.assertEqual(list(StockMovement.objects.values()), moves)
        item.refresh_from_db()
        self.assertEqual((item.unit_cost, item.cmv), (D(5), D(10)))
        self.product.refresh_from_db()
        self.assertEqual((self.product.quantity, self.product.value), stock)
        d = dict(start=sale.date, end=sale.date, status='CONFIRMED')
        self.assertEqual(sales_summary(Sale.objects.all())['cmv'], D(3))
        self.assertEqual(channel_summary(d)[0]['cmv'], D(3))
        from django.core import signing
        from apps.reporting.drilldown import sources
        token = signing.dumps({'kind': 'sale', 'field': 'cmv', 'label': 'CMV'}, salt='dre-source-v1')
        self.assertEqual(sources(token, d)[2], D(3))
        from apps.reporting.sales_sheet import cells
        self.assertEqual(cells(result, [{'key': 'cmv'}])[0]['value'], D(3))
        dataset = sales_dataset(self.actor, d)
        self.assertEqual(dataset.rows[0][dataset.headers.index('CMV histórico')], D(3))
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse('dashboard')).context['totals']['cmv'], D(3))
        self.assertEqual(self.client.get(reverse('dre')).context['report']['sales']['cmv'], D(3))
        self.assertEqual(D(self.client.get(reverse('sale_result', args=[sale.pk])).json()['cmv']), D(3))
        self.assertContains(self.client.get(reverse('sale_detail', args=[sale.pk])), 'Correção de CMV')

    def test_repeat_correction_cancel_recovery_and_idempotency(self):
        sale = self.confirmed()
        args = self.args(sale)
        correct_cost(**args); sale = correct_cost(**args)
        self.assertEqual(SaleCostRevision.objects.count(), 1)
        args['costs'] = {sale.items.get().pk: D(2)}
        with self.assertRaises(ValidationError): correct_cost(**args)
        sale = correct_cost(**self.args(sale, '2'))
        self.assertEqual(sale.effective_cmv, D(4))
        sale = cancel(actor=self.actor, sale_id=sale.pk, reason='Teste')
        self.assertEqual(sales_summary(Sale.objects.all())['cmv'], 0)
        self.product.refresh_from_db(); self.assertEqual(self.product.quantity, 10)
        sale = recover_sale(actor=self.actor, sale_id=sale.pk, revision=sale.revision,
                            key=uuid4(), fees=sale.fees, reason='Recuperar')
        self.assertEqual(sale.effective_cmv, D(4))
        self.assertEqual(sales_summary(Sale.objects.all())['cmv'], D(4))
        sale = correct_cost(**self.args(sale, '5'))
        self.assertEqual(sale.cmv_adjustment, 0)

    def test_invalid_costs_stale_revision_and_permissions(self):
        sale = self.confirmed()
        for cost in ['-1', 'NaN', '1.1234567', '1000000000000']:
            with self.subTest(cost=cost), self.assertRaises(ValidationError):
                correct_cost(**self.args(sale, cost))
        args = self.args(sale); args['costs'] = {}
        with self.assertRaises(ValidationError): correct_cost(**args)
        args = self.args(sale); args['actor'] = self.operator
        with self.assertRaises(PermissionDenied): correct_cost(**args)
        args = self.args(sale); args['revision'] -= 1
        with self.assertRaises(ValidationError): correct_cost(**args)
        args = self.args(sale); args['reason'] = ' '
        with self.assertRaises(ValidationError): correct_cost(**args)
        self.client.force_login(self.operator)
        url = reverse('sale_correct_cost', args=[sale.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertFalse(SaleCostRevision.objects.exists())

    def test_preview_is_required_and_tamper_protected(self):
        sale = self.confirmed(); item = sale.items.get()
        self.client.force_login(self.actor)
        url = reverse('sale_correct_cost', args=[sale.pk])
        data = dict(key=str(uuid4()), revision=sale.revision, reason='Conferência', **{f'cost_{item.pk}': '1,50'})
        response = self.client.post(url, data)
        self.assertContains(response, 'Confirmar correção do CMV')
        self.assertFalse(SaleCostRevision.objects.exists())
        token = response.context['preview_token']
        tampered = dict(data, confirm='1', preview_token=token, **{f'cost_{item.pk}': '2,00'})
        self.assertContains(self.client.post(url, tampered), 'Os valores mudaram')
        self.assertContains(self.client.post(url, dict(data, confirm='1')), 'Prévia ausente')
        response = self.client.post(url, dict(data, confirm='1', preview_token=token))
        self.assertRedirects(response, reverse('sale_detail', args=[sale.pk]))
        sale.refresh_from_db(); self.assertEqual(sale.effective_cmv, D(3))

    def test_correction_survives_location_change(self):
        from apps.inventory.models import StockLocation
        from apps.sales.corrections import correct_sale, FIELDS
        sale = correct_cost(**self.args(self.confirmed()))
        location = StockLocation.objects.create(name='Destino sintético')
        from apps.inventory.services import execute
        execute(actor=self.actor, key=uuid4(), kind='RECEIPT', date=sale.date,
                reason='Referência', product_id=self.product.pk, location_id=location.pk,
                quantity=D(10), cost=D(5))
        sale = correct_sale(actor=self.actor, sale_id=sale.pk, revision=sale.revision,
                            key=uuid4(), reason='Depósito correto', location_id=location.pk,
                            values={name: getattr(sale, name) for name in FIELDS})
        self.assertEqual(sale.effective_cmv, D(3))
        self.assertEqual(sale.cmv, D(10))
        sale = cancel(actor=self.actor, sale_id=sale.pk, reason='Teste')
        self.assertEqual(sale.effective_cmv, D(3))

    def test_multiple_items_and_zero_cost(self):
        from apps.products.models import Product
        from .services import confirm
        second = Product.objects.create(sku='SECOND', name='Outro item')
        self.receive(second, D(10), D(3))
        sale = self.draft(items=[(self.product.pk, D(2)), (second.pk, D(3))])
        sale = confirm(actor=self.actor, sale_id=sale.pk, revision=sale.revision)
        items = list(sale.items.all())
        sale = correct_cost(actor=self.actor, sale_id=sale.pk, revision=sale.revision,
                            key=uuid4(), reason='Custos conferidos',
                            costs={items[0].pk: D(0), items[1].pk: D('1.123456')})
        self.assertEqual(sale.effective_cmv, D('3.370368'))
        self.assertEqual(sale.cmv, D(19))

    @skipUnless(connection.vendor == 'postgresql', 'PostgreSQL trigger protection')
    def test_sql_changes_and_history_edits_blocked(self):
        sale = correct_cost(**self.args(self.confirmed()))
        for action in [
            lambda: Sale.objects.filter(pk=sale.pk).update(cmv_adjustment=0),
            lambda: Sale.objects.filter(pk=sale.pk).update(cmv=0),
            lambda: SaleCostRevision.objects.filter(sale=sale).update(reason='Mutação'),
            lambda: SaleCostRevision.objects.filter(sale=sale).delete(),
        ]:
            with self.assertRaises(DatabaseError), transaction.atomic(): action()
