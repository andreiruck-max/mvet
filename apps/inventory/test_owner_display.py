from decimal import Decimal as D
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.core.models import Company
from apps.products.models import Product, ProductComposition
from .models import StockBalance, StockOperation
from .selectors import owner_position, kit_summary
from .tests import StockFixtures, DAY


@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class OwnerDisplayTests(StockFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.op()
        Company.objects.get_or_create(pk=2, defaults={'name':'Agro sintética', 'active':False})
        # A deliberately different secondary projection must not leak into primary reads.
        StockBalance.objects.create(company_id=2,product=self.p,location=self.loc,
            quantity=D('100'),value=D('9900'),average_cost=D('99'))
        Product.objects.filter(pk=self.p.pk).update(quantity=D('110'),value=D('9950'),average_cost=D('90.454545'))
        self.p.refresh_from_db()
        self.kit=Product.objects.create(sku='KIT-OWNER',name='Kit teste',kind='KIT')
        ProductComposition.objects.create(kit=self.kit,component=self.p,quantity=D('2'))
        self.client.force_login(self.actor)

    def test_owner_summary_and_kit_ignore_global_projection(self):
        self.assertEqual(owner_position(self.p),(D('10'),D('50'),D('5')))
        _,quantity,cost=kit_summary(self.kit)
        self.assertEqual((quantity,cost),(5,D('10')))

    def test_lookup_with_and_without_depot_uses_owner_quantity_and_cost(self):
        for product, quantity, cost in [(self.p,D('10'),D('5')),(self.kit,D('5'),D('10'))]:
            for location in ['',str(self.loc.pk)]:
                response=self.client.get(reverse('product_lookup'),{'q':product.sku,'location':location})
                self.assertEqual(response.status_code,200)
                row=response.json()['results'][0]
                self.assertEqual(D(row['quantity']),quantity)
                self.assertEqual(D(row['cost']),cost)

    def test_detail_has_only_primary_balances_and_totals(self):
        response=self.client.get(reverse('product_detail',args=[self.p.pk]))
        self.assertEqual(response.status_code,200)
        product=response.context['product']
        self.assertEqual((product.owner_quantity,product.owner_value,product.owner_average),(D('10'),D('50'),D('5')))
        self.assertEqual({b.company_id for b in response.context['balances']},{1})

    def test_secondary_operation_is_hidden_and_cannot_be_reversed_by_url(self):
        from uuid import uuid4
        operation=StockOperation.objects.create(company_id=2,actor=self.actor,
            date=DAY,kind='RECEIPT',reason='Operação secundária confidencial',
            key=uuid4(),fingerprint='secondary-http-fixture')
        response=self.client.get(reverse('operations'))
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,operation.reason)
        detail=reverse('operation_detail',args=[operation.pk])
        self.assertEqual(self.client.get(detail).status_code,404)
        self.assertEqual(self.client.post(detail,{'reason':'Tentativa','date':DAY,'key':uuid4()}).status_code,404)
        self.assertFalse(StockOperation.objects.filter(reversal_of=operation).exists())

    def test_count_preview_shows_only_primary_position(self):
        response=self.client.get(reverse('product_count',args=[self.p.pk,self.loc.pk]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['balance'].company_id,1)
        self.assertEqual(response.context['balance'].quantity,D('10'))
