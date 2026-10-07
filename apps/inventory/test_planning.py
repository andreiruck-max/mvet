from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.sales import services as sales
from apps.products.models import Product
from apps.purchases.models import Supplier
from apps.purchases import services as purchases
from .services import execute
from .planning import purchase_plan


class PlanningTests(Fixture, TestCase):
    def plan(self, **kwargs):
        return purchase_plan(location=self.location, zero_days=30, history_days=30, coverage_days=30, **kwargs)

    def test_zero_with_old_movement_excluded_positive_and_unknown_retained(self):
        zero = Product.objects.create(sku='0', name='Zerado', minimum=4)
        unknown = Product.objects.create(sku='3', name='Sem histórico', minimum=2)
        self.receive(zero, D(1), D(2))
        execute(actor=self.actor, key=uuid4(), kind='ISSUE', date=timezone.localdate(),
                reason='Teste', product_id=zero.pk, location_id=self.location.pk, quantity=D(1))
        future = timezone.localdate()+timedelta(days=30)
        rows, totals = self.plan(today=future)
        self.assertEqual(totals['excluded_count'], 1)
        self.assertEqual({r['product'].pk for r in rows}, {self.product.pk, unknown.pk})
        self.assertEqual(next(r for r in rows if r['product']==unknown)['suggested'], 2)
        rows, _ = self.plan(today=future, show_excluded=True)
        self.assertTrue(next(r for r in rows if r['product']==zero)['excluded'])
        self.assertEqual(self.plan(today=future-timedelta(days=1))[1]['excluded_count'], 0)
        zero.refresh_from_db(); self.assertTrue(zero.active)

    def test_demand_pending_purchases_and_cancellation(self):
        sale = self.draft(items=[(self.product.pk,D(8))])
        sale = sales.confirm(actor=self.actor, sale_id=sale.pk, revision=sale.revision)
        supplier = Supplier.objects.create(legal_name='Teste')
        purchase = purchases.save_draft(actor=self.actor, key=uuid4(),
            data={'supplier':supplier, 'document':'SYNTHETIC', 'series':'', 'date':timezone.localdate(),
                  'location':self.location, 'discount':D(0), 'freight':D(0), 'other_costs':D(0), 'notes':''},
            items=[(self.product.pk,D(3),D(1))], installments=[(timezone.localdate(),D(3),'')])
        purchases.confirm(actor=self.actor, purchase_id=purchase.pk, revision=purchase.revision)
        row = self.plan()[0][0]
        self.assertEqual(row['sold'], 8); self.assertEqual(row['pending'], 3)
        self.assertEqual(row['suggested'], 3)
        sales.cancel(actor=self.actor, sale_id=sale.pk, reason='Teste')
        self.assertEqual(self.plan()[0][0]['sold'], 0)
        self.assertEqual(self.plan()[0][0]['suggested'], 0)

    def test_default_positive_can_be_unchecked_and_plan_permissions(self):
        zero = Product.objects.create(sku='ZERO-SYNTHETIC', name='Zerado')
        self.client.force_login(self.actor)
        self.assertNotContains(self.client.get(reverse('products')), zero.sku)
        self.assertContains(self.client.get(reverse('products'), {'positive':'0'}), zero.sku)
        response = self.client.get(reverse('purchase_planning'))
        self.assertContains(response, 'Sem histórico')
        self.assertEqual(self.client.get(reverse('purchase_planning'), {'location': self.location.pk, 'zero_days':0}).context['page'].paginator.count, 0)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('purchase_planning')).status_code, 403)
