import json
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch
from uuid import uuid4
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.sales.tests import Fixture
from apps.products.pricing import configure_pricing, sale_price
from apps.products.models import Product
from apps.core.models import AuditLog
from apps.reporting.datasets import build
from .models import StockBalance, StockLocation, StockMovement, InventoryReconciliation
from .reconciliation import reconcile
from .services import execute


class PricingTests(Fixture, TestCase):
    def test_default_override_zero_and_master_only(self):
        self.assertEqual(self.company.default_markup,D(35))
        self.assertEqual(sale_price(self.product,D('5'),D(35)),D('6.75'))
        configure_pricing(actor=self.actor,markup=D(50))
        self.company.refresh_from_db()
        self.assertEqual(sale_price(self.product,D('5'),self.company.default_markup),D('7.50'))
        configure_pricing(actor=self.actor,product_id=self.product.pk,markup=D(0))
        self.product.refresh_from_db()
        self.assertEqual(sale_price(self.product,D('5'),D(50)),D('5.00'))
        configure_pricing(actor=self.actor,product_id=self.product.pk,markup=None)
        self.product.refresh_from_db()
        self.assertEqual(sale_price(self.product,D('5'),D(50)),D('7.50'))
        with self.assertRaises(PermissionDenied):configure_pricing(actor=self.operator,markup=D(70))
        with self.assertRaises(ValidationError):configure_pricing(actor=self.actor,markup=D(-1))
        self.assertEqual(AuditLog.objects.filter(operation='configure_pricing').count(),3)

    def test_employee_price_without_cost_and_full_without_markup(self):
        full=StockLocation.objects.create(name='Full Mercado Livre')
        self.company.default_stock_location=self.location;self.company.save()
        execute(actor=self.actor,key=uuid4(),kind='RECEIPT',date=timezone.localdate(),reason='Teste',product_id=self.product.pk,location_id=full.pk,quantity=D(1),cost=D(99))
        self.client.force_login(self.operator)
        page=self.client.get(reverse('products'))
        self.assertContains(page,'R$ 6,75')
        for hidden in ['Custo médio','Valor do estoque','Editar preço','markup']:
            self.assertNotContains(page,hidden)
        for url in [reverse('stock_pricing'),reverse('product_pricing',args=[self.product.pk]),reverse('inventory_reconcile')]:
            self.assertEqual(self.client.get(url).status_code,403)
            self.assertEqual(self.client.post(url,{'markup':'1'}).status_code,403)
        data=self.client.get(reverse('product_lookup'),{'q':self.product.sku}).json()['results'][0]
        self.assertNotIn('cost',data);self.assertEqual(data['sale_price'],'6.75')
        data=self.client.get(reverse('product_lookup'),{'q':self.product.sku,'location':full.pk}).json()['results'][0]
        self.assertNotIn('sale_price',data)
        self.assertNotContains(self.client.get(reverse('products'),{'location':full.pk}),'Preço de venda')
        detail=self.client.get(reverse('product_detail',args=[self.product.pk]))
        self.assertContains(detail,'R$ 6,75');self.assertNotContains(detail,'133,65')
        exported=build('stock',self.actor,{'location':str(self.location.pk)})
        self.assertEqual(exported.rows[0][-1],D('6.75'))
        exported=build('stock',self.actor,{'location':str(full.pk)})
        self.assertNotIn('PREÇO DE VENDA',exported.headers)


class ReconciliationTests(Fixture,TestCase):
    def payload(self, **overrides):
        item=dict(sku=self.product.sku,name='Nome externo não substitui cadastro',unit='UN',quantity='7',cost='8',value='56')
        item.update(overrides)
        return json.dumps(dict(version=2,date=str(timezone.localdate()),locations=[dict(location=self.location.name,complete=True,items=[item])]))

    def apply(self, raw):
        preview=reconcile(actor=self.actor,raw=raw)
        return reconcile(actor=self.actor,raw=raw,commit=True,expected_revision=preview['revision'])

    def test_preview_commit_replay_and_preserved_cmv(self):
        sale=self.confirmed()
        original=sale.cmv
        before=StockMovement.objects.count()
        raw=self.payload()
        preview=reconcile(actor=self.actor,raw=raw)
        self.assertEqual(StockMovement.objects.count(),before)
        self.assertEqual(preview['changes'][0]['quantity'],'7.0000')
        report=self.apply(raw)
        self.assertTrue(report['committed'])
        self.product.refresh_from_db();sale.refresh_from_db()
        self.assertEqual((self.product.quantity,self.product.value,self.product.average_cost),(7,56,8))
        self.assertEqual(sale.cmv,original)
        self.assertEqual(self.product.name,'Produto teste')
        self.assertTrue(reconcile(actor=self.actor,raw=raw,commit=True)['already_applied'])
        self.assertEqual(InventoryReconciliation.objects.count(),1)
        with self.assertRaises(ValidationError): self.apply(self.payload(quantity='8',value='64'))
        call_command('check_inventory')

    def test_later_movements_preserved_and_new_and_absent_products(self):
        base=timezone.localdate()-timedelta(days=1)
        # Existing fixture receipt and sale occur AFTER the baseline.
        self.confirmed()
        raw=json.loads(self.payload());raw['date']=str(base)
        raw['locations'][0]['items'].append(dict(sku='NEW',name='Novo sintético',unit='UN',quantity='2',cost='3',value='6'))
        other=Product.objects.create(sku='ABSENT',name='Ausente da base')
        execute(actor=self.actor,key=uuid4(),kind='RECEIPT',date=base,reason='Teste',product_id=other.pk,location_id=self.location.pk,quantity=D(3),cost=D(1))
        self.apply(json.dumps(raw))
        self.product.refresh_from_db();other.refresh_from_db()
        # target base 7/56 + later receipt 10/50 - sale 2/10
        self.assertEqual((self.product.quantity,self.product.value),(15,96))
        self.assertEqual(other.quantity,0)
        self.assertEqual(Product.objects.get(sku='NEW').value,6)
        call_command('check_inventory')

    def test_negative_base_balance_reconciles_without_receipt_variance(self):
        from apps.sales.services import confirm
        sale=self.draft(items=[(self.product.pk,D(12))])
        confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)
        self.apply(self.payload())
        self.product.refresh_from_db()
        self.assertEqual((self.product.quantity,self.product.value),(7,56))
        self.assertEqual(StockMovement.objects.filter(operation__kind='RECONCILE').get().cost_variance,0)
        call_command('check_inventory')

    def test_stale_preview_permissions_and_invalid_file_atomic(self):
        raw=self.payload();preview=reconcile(actor=self.actor,raw=raw)
        self.receive(self.product,D(1),D(5))
        with self.assertRaises(ValidationError):reconcile(actor=self.actor,raw=raw,commit=True,expected_revision=preview['revision'])
        with self.assertRaises(PermissionDenied):reconcile(actor=self.operator,raw=raw)
        for bad in [self.payload(value='57'), self.payload(quantity='-2'), self.payload(cost='NaN')]:
            with self.assertRaises(ValidationError):self.apply(bad)
        self.assertFalse(InventoryReconciliation.objects.exists())

    def test_upload_preview_and_apply(self):
        self.client.force_login(self.actor)
        url=reverse('inventory_reconcile')
        response=self.client.post(url,{'file':SimpleUploadedFile('snapshot.json',self.payload().encode())})
        self.assertContains(response,'Aplicar conciliação no MVet')
        token=response.context['token']
        response=self.client.post(url,{'action':'apply','token':token})
        self.assertContains(response,'Conciliação já aplicada')
        self.assertEqual(InventoryReconciliation.objects.count(),1)
