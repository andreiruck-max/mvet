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
        needed, _ = self.plan(today=future, show_excluded=True, need='needed')
        self.assertEqual({r['product'].pk for r in needed}, {unknown.pk})
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
        self.assertEqual(len(self.plan(need='needed')[0]), 1)
        sales.cancel(actor=self.actor, sale_id=sale.pk, reason='Teste')
        self.assertEqual(self.plan()[0][0]['sold'], 0)
        self.assertEqual(self.plan()[0][0]['suggested'], 0)
        self.assertEqual(self.plan(need='needed')[0], [])

    def test_default_positive_can_be_unchecked_and_plan_permissions(self):
        zero = Product.objects.create(sku='ZERO-SYNTHETIC', name='Zerado')
        self.client.force_login(self.actor)
        self.assertNotContains(self.client.get(reverse('products')), zero.sku)
        self.assertContains(self.client.get(reverse('products'), {'positive':'0'}), zero.sku)
        response = self.client.get(reverse('purchase_planning'))
        self.assertEqual(response.context['page'].paginator.count, 0)
        self.assertContains(self.client.get(reverse('purchase_planning'), {'need': 'all'}), 'Sem histórico')
        self.assertEqual(self.client.get(reverse('purchase_planning'), {'location': self.location.pk, 'zero_days':0}).context['page'].paginator.count, 0)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('purchase_planning')).status_code, 403)

    def test_need_filter_before_pagination_and_session(self):
        Product.objects.bulk_create([Product(sku=f'NEED-{i:03}', name='Reposição', minimum=2) for i in range(51)])
        Product.objects.create(sku='NO-NEED', name='Sem demanda')
        self.client.force_login(self.actor)
        url = reverse('purchase_planning')
        response = self.client.get(url)
        self.assertEqual(response.context['page'].paginator.count, 51)
        self.assertEqual(response.context['totals']['product_count'], 53)
        self.assertEqual(response.context['totals']['suggested_count'], 51)
        self.assertTrue(all(row['suggested'] > 0 for row in response.context['page']))
        response = self.client.get(url, {'page': 2})
        self.assertEqual(len(response.context['page']), 1)
        self.assertEqual(self.client.get(url, {'need': 'all'}).context['page'].paginator.count, 53)
        self.assertEqual(self.client.get(url).context['form'].cleaned_data['need'], 'all')
        response = self.client.get(url, {'need': 'needed', 'q': 'NO-NEED'})
        self.assertEqual(response.context['page'].paginator.count, 0)
        self.assertContains(response, 'Nenhum produto para estes filtros.')
        self.assertEqual(self.client.get(url, {'need': 'invalid'}).context['page'].paginator.count, 0)

    def test_exports_all_filtered_rows_and_selected_products(self):
        from io import BytesIO
        from zipfile import ZipFile
        from xml.etree.ElementTree import fromstring
        from apps.reporting.files import NS
        from unittest.mock import patch
        Product.objects.bulk_create([Product(sku=f'EXPORT-{i:03}', name='Cotação', minimum=D('1.2345')) for i in range(51)])
        self.client.force_login(self.actor)
        url = reverse('purchase_planning')
        response = self.client.get(url, {'export': 'xlsx', 'page': 2})
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as book:
            root = fromstring(book.read('xl/worksheets/sheet1.xml'))
        strings = [n.text for n in root.iter('{'+NS+'}t')]
        self.assertIn('EXPORT-000', strings)
        self.assertIn('EXPORT-050', strings)
        self.assertNotIn(self.product.sku, strings)
        self.assertNotIn('CMV', strings)
        self.assertEqual(len([n for n in root.iter('{'+NS+'}v') if n.text == '1.2345']), 51)
        chosen = Product.objects.get(sku='EXPORT-050')
        response = self.client.get(url, {'export':'xlsx', 'scope':'selected', 'product':[chosen.pk]})
        with ZipFile(BytesIO(response.content)) as book:
            xml = book.read('xl/worksheets/sheet1.xml').decode()
        self.assertIn('EXPORT-050', xml)
        self.assertNotIn('EXPORT-000', xml)
        with patch('apps.inventory.planning_exports.pdf', return_value=b'%PDF-test') as render:
            response = self.client.get(url, {'export':'pdf', 'scope':'selected', 'product':[chosen.pk]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(render.call_args.args[0].rows[0][3], '1,2345')
        response = self.client.get(url, {'export':'pdf', 'q':chosen.sku})
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_export_rejects_invalid_selection_filters_and_permissions(self):
        from django.contrib.auth.models import Permission
        self.client.force_login(self.actor)
        url = reverse('purchase_planning')
        for params in [
            {'export':'pdf', 'scope':'selected'},
            {'export':'pdf', 'scope':'selected', 'product':['bad']},
            {'export':'pdf', 'scope':'selected', 'product':[self.product.pk]},
            {'export':'pdf', 'zero_days':0},
            {'export':'csv'},
            {'export':'pdf', 'scope':'other'},
            {'export':'pdf'},
        ]:
            self.assertEqual(self.client.get(url, params).status_code, 400)
        self.operator.user_permissions.add(*Permission.objects.filter(codename__in=['view_stock','operate_purchases']))
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertNotContains(self.client.get(url), 'Exportar Excel')
        self.assertEqual(self.client.get(url, {'export':'xlsx'}).status_code, 403)
        self.operator.user_permissions.clear()
        self.operator.user_permissions.add(Permission.objects.get(codename='export_purchases'))
        self.assertEqual(self.client.get(url, {'export':'xlsx'}).status_code, 403)
