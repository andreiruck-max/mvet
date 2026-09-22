from decimal import Decimal as D
from importlib import import_module
from types import SimpleNamespace
from urllib.parse import urlencode
from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, RequestFactory
from django.urls import reverse
from apps.sales.tests import Fixture
from apps.core.models import AuditLog
from apps.core.navigation import return_url
from apps.products.models import Product
from apps.products.services import inactivate_product, remove_product
from .counting import count_snapshot, apply_count
from .models import StockLocation, StockBalance, StockMovement
from .selectors import catalog


class CountingTests(Fixture, TestCase):
    def count(self, quantity, token=None, actor=None):
        return apply_count(actor=actor or self.actor, product_id=self.product.pk, location_id=self.location.pk,
                           snapshot=token or count_snapshot(self.actor, self.product, self.location),
                           counted=D(quantity), reason='Conferência física')

    def test_count_down_up_no_change_and_idempotency(self):
        other = StockLocation.objects.create(name='Outro depósito')
        token = count_snapshot(self.actor, self.product, self.location)
        down = self.count('7', token)
        self.assertEqual(D(down['difference']), -3)
        self.assertEqual(self.count('7', token), down)
        self.assertEqual(AuditLog.objects.filter(operation='stock_count').count(), 1)
        with self.assertRaises(ValidationError): self.count('8', token)
        self.count('12')
        balance = StockBalance.objects.get(product=self.product, location=self.location)
        self.assertEqual((balance.quantity,balance.value,balance.average_cost),(12,60,5))
        self.assertFalse(StockBalance.objects.filter(location=other).exists())
        before = StockMovement.objects.count()
        same = self.count('12')
        self.assertIsNone(same['operation'])
        self.assertEqual(StockMovement.objects.count(),before)
        self.count('0')
        balance.refresh_from_db();self.assertEqual(balance.value,0)

    def test_stale_tampered_and_unauthorized_counts_blocked(self):
        token=count_snapshot(self.actor,self.product,self.location)
        self.receive(self.product,D(1),D(5))
        with self.assertRaises(ValidationError):self.count('7',token)
        with self.assertRaises(ValidationError):self.count('7',token+'bad')
        with self.assertRaises(PermissionDenied):self.count('7',token,actor=self.operator)
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.location).quantity,11)

    def test_filter_format_and_safe_return(self):
        self.company.default_stock_location=self.location;self.company.save()
        self.receive(self.product,D(1000),D(5))
        zero=Product.objects.create(sku='ZERO',name='Sem saldo')
        other=StockLocation.objects.create(name='Outro')
        self.assertEqual(catalog({'positive':'1','location':str(self.location.pk)}).count(),1)
        self.assertEqual(catalog({'positive':'1','location':str(other.pk)}).count(),0)
        self.client.force_login(self.actor)
        r=self.client.get(reverse('products'),{'positive':'1'})
        self.assertContains(r,'R$ 5.050,00')
        self.assertNotContains(r,'Sem saldo')
        origin=reverse('products')+'?location='+str(self.location.pk)+'&positive=1&page=2'
        r=self.client.get(reverse('product_edit',args=[self.product.pk]),{'next':origin})
        self.assertEqual(r.context['back_url'],origin)
        for unsafe in ['https://evil.example','//evil.example','/\\evil.example','javascript:alert(1)']:
            req=RequestFactory().get('/estoque/produtos/1/',{'next':unsafe})
            self.assertEqual(return_url(req),reverse('products'))

    def test_inactivate_preserves_stock_and_delete_only_unused(self):
        inactivate_product(actor=self.actor,pk=self.product.pk)
        self.product.refresh_from_db();self.assertFalse(self.product.active)
        self.assertEqual(self.product.quantity,10)
        remove_product(actor=self.actor,pk=self.product.pk)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        unused=Product.objects.create(sku='UNUSED',name='Sem histórico')
        remove_product(actor=self.actor,pk=unused.pk)
        self.assertFalse(Product.objects.filter(pk=unused.pk).exists())
        with self.assertRaises(PermissionDenied):inactivate_product(actor=self.operator,pk=self.product.pk)

    def test_count_http_preserves_filters_and_csrf(self):
        from django.test import Client
        self.client.force_login(self.actor)
        origin=reverse('products')+'?positive=1&location='+str(self.location.pk)
        url=reverse('product_count',args=[self.product.pk,self.location.pk])+'?'+urlencode({'next':origin})
        r=self.client.get(url);token=r.context['form'].initial['snapshot']
        data={'snapshot':token,'counted':'8','reason':'Conferência física'}
        secured=Client(enforce_csrf_checks=True);secured.force_login(self.actor)
        self.assertEqual(secured.post(url,data).status_code,403)
        self.assertRedirects(self.client.post(url,data),origin)
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.location).quantity,8)

    def test_cleanup_only_unused_duplicate_and_setup_canonical_name(self):
        migration=import_module('apps.inventory.migrations.0007_remove_unused_duplicate_full')
        editor=SimpleNamespace(connection=connection)
        old=StockLocation.objects.create(name='Estoque Full')
        full=StockLocation.objects.create(name='Full Mercado Livre')
        migration.clean_unused_full(apps,editor)
        self.assertFalse(StockLocation.objects.filter(pk=old.pk).exists())
        old=StockLocation.objects.create(name='Estoque Full')
        self.company.default_stock_location=old;self.company.save()
        migration.clean_unused_full(apps,editor)
        self.assertTrue(StockLocation.objects.filter(pk=old.pk).exists())
