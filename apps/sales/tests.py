from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from django.contrib.auth.models import User, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, connections, close_old_connections, transaction, DatabaseError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from apps.core.models import Company, AuditLog
from apps.products.models import Product
from apps.products.services import set_components
from apps.inventory.models import StockLocation, StockOperation, StockMovement
from apps.inventory.services import execute, reverse as reverse_stock
from .models import Sale, SaleItem, SaleConsumption, SalesChannel, TaxRule
from .services import save_draft, confirm, cancel, save_configuration

class Fixture:
    def setUp(self):
        self.company=Company.objects.create(pk=1)
        self.actor=User.objects.create_superuser('owner')
        self.operator=User.objects.create_user('operator')
        self.operator.user_permissions.add(Permission.objects.get(codename='operate_sales'))
        self.location=StockLocation.objects.create(name='Loja')
        self.channel=SalesChannel.objects.create(name='Canal teste')
        self.rule=TaxRule.objects.create(name='Regra teste',rate=D('5'),starts_on=self.company.cutover_date,base='REVENUE')
        self.product=Product.objects.create(sku='TEST-1',name='Produto teste')
        self.receive(self.product,D('10'),D('5'))
    def receive(self,product,qty,cost):
        return execute(actor=self.actor,key=uuid4(),kind='RECEIPT',date=timezone.localdate(),reason='Teste sintético',product_id=product.pk,location_id=self.location.pk,quantity=qty,cost=cost)
    def data(self,**changes):
        data={'date':timezone.localdate(),'invoice_number':'100','invoice_series':'','channel':self.channel,'location':self.location,'products_amount':D('100'),'discount':D('10'),'shipping_received':D('5'),'shipping_paid':D('7'),'fees':D('3'),'difal':D('1'),'commission':D('2'),'other_costs':D('4'),'tax_rule':self.rule,'tax_override':None,'tax_reason':'','notes':''}
        data.update(changes);return data
    def draft(self,items=None,**changes):
        return save_draft(actor=self.operator,key=uuid4(),data=self.data(**changes),items=items or [(self.product.pk,D('2'))])
    def confirmed(self,**changes):
        sale=self.draft(**changes);return confirm(actor=self.operator,sale_id=sale.pk,revision=sale.revision)

class SalesTests(Fixture,TestCase):
    def test_full_product_name_is_preserved(self):
        self.product.name="P"*240;self.product.save(update_fields=["name"])
        sale=self.confirmed();self.assertEqual(sale.items.get().name_snapshot,"P"*240)

    def test_draft_then_confirm_financial_formula(self):
        sale=self.draft();self.product.refresh_from_db();self.assertEqual(self.product.quantity,10)
        sale=confirm(actor=self.operator,sale_id=sale.pk,revision=sale.revision)
        self.assertEqual(sale.cmv,D('10'));self.assertEqual(sale.revenue,D('95'));self.assertEqual(sale.tax_amount,D('4.75'));self.assertEqual(sale.contribution,D('63.25'))
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,8)
        item=sale.items.get();self.assertEqual(item.unit_cost,5);self.assertEqual(item.sku_snapshot,'TEST-1')
        self.assertEqual(SaleConsumption.objects.count(),1)
    def test_creation_and_confirmation_idempotent(self):
        key=uuid4();data=self.data();items=[(self.product.pk,D('1'))]
        first=save_draft(actor=self.operator,key=key,data=data,items=items)
        self.assertEqual(first.pk,save_draft(actor=self.operator,key=key,data=data,items=items).pk)
        with self.assertRaises(ValidationError):save_draft(actor=self.operator,key=key,data=self.data(products_amount=D('99')),items=items)
        confirm(actor=self.operator,sale_id=first.pk,revision=1);confirm(actor=self.operator,sale_id=first.pk,revision=1)
        self.assertEqual(StockOperation.objects.filter(kind='SALE_OUT').count(),1)
    def test_multiple_items_duplicate_product_and_snapshot(self):
        other=Product.objects.create(sku='SECOND',name='Segundo');self.receive(other,D('3'),D('7'))
        sale=self.draft(items=[(self.product.pk,D('1')),(other.pk,D('2')),(self.product.pk,D('3'))])
        sale=confirm(actor=self.operator,sale_id=sale.pk,revision=1);self.assertEqual(sale.cmv,34)
        self.receive(self.product,D('10'),D('20'));sale.refresh_from_db();self.assertEqual(sale.cmv,34)
        self.rule.rate=D('20');self.rule.save();self.assertEqual(sale.tax_snapshot['rate'],'5.0000')
    def test_shortage_rolls_back_every_item(self):
        sale=self.draft(items=[(self.product.pk,D('2')),(self.product.pk,D('20'))])
        before=StockMovement.objects.count()
        with self.assertRaises(ValidationError):confirm(actor=self.operator,sale_id=sale.pk,revision=1)
        self.product.refresh_from_db();sale.refresh_from_db()
        self.assertEqual(self.product.quantity,10);self.assertEqual(sale.status,'DRAFT');self.assertEqual(StockMovement.objects.count(),before);self.assertFalse(SaleConsumption.objects.exists())
    def test_local_shortage_is_atomic(self):
        empty=StockLocation.objects.create(name='Vazio');sale=self.draft(location=empty)
        with self.assertRaises(ValidationError):confirm(actor=self.operator,sale_id=sale.pk,revision=1)
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,10)
    def test_cancel_after_receipt_uses_historic_value(self):
        sale=self.confirmed();self.receive(self.product,D('10'),D('20'))
        result=cancel(actor=self.operator,sale_id=sale.pk,reason='Cliente desistiu')
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,20);self.assertEqual(self.product.value,250);self.assertEqual(self.product.average_cost,D('12.5'))
        self.assertEqual(result.cmv,10);self.assertEqual(result.status,'CANCELLED')
        cancel(actor=self.operator,sale_id=sale.pk,reason='Repetição');self.assertEqual(StockOperation.objects.filter(kind='SALE_RETURN').count(),1)
    def test_kit_cancel_uses_consumed_components(self):
        kit=Product.objects.create(sku='KIT',name='Kit',kind='KIT');other=Product.objects.create(sku='OTHER',name='Outro')
        set_components(actor=self.actor,kit_id=kit.pk,items=[(self.product.pk,D('2'))])
        sale=self.draft(items=[(kit.pk,D('2'))]);sale=confirm(actor=self.operator,sale_id=sale.pk,revision=1)
        self.assertEqual(sale.cmv,20)
        set_components(actor=self.actor,kit_id=kit.pk,items=[(other.pk,D('1'))])
        cancel(actor=self.operator,sale_id=sale.pk,reason='Cancelamento kit')
        self.product.refresh_from_db();other.refresh_from_db();self.assertEqual(self.product.quantity,10);self.assertEqual(other.quantity,0)
    def test_empty_kit_rejected(self):
        kit=Product.objects.create(sku='KIT',name='Kit',kind='KIT');sale=self.draft(items=[(kit.pk,D('1'))])
        with self.assertRaises(ValidationError):confirm(actor=self.operator,sale_id=sale.pk,revision=1)
    def test_generic_reversal_cannot_change_sale(self):
        sale=self.confirmed()
        with self.assertRaises(ValidationError):reverse_stock(actor=self.actor,operation_id=sale.stock_operation_id,key=uuid4(),date=timezone.localdate(),reason='Bypass')
        sale=cancel(actor=self.actor,sale_id=sale.pk,reason='OK')
        with self.assertRaises(ValidationError):reverse_stock(actor=self.actor,operation_id=sale.return_operation_id,key=uuid4(),date=timezone.localdate(),reason='Bypass')
    def test_draft_cancel_no_stock(self):
        sale=self.draft();sale=cancel(actor=self.operator,sale_id=sale.pk,reason='Duplicado')
        self.assertIsNone(sale.return_operation_id)
        with self.assertRaises(ValidationError):confirm(actor=self.operator,sale_id=sale.pk,revision=2)
    def test_nf_normalization_unique_including_cancelled(self):
        sale=self.draft(invoice_number='00100',invoice_series='01');cancel(actor=self.actor,sale_id=sale.pk,reason='Teste')
        with self.assertRaises(ValidationError):self.draft(invoice_number='100',invoice_series='1')
        self.draft(invoice_number='100',invoice_series='2')
    def test_edit_and_stale_revision(self):
        sale=self.draft();save_draft(actor=self.operator,key=sale.key,sale_id=sale.pk,revision=1,data=self.data(notes='Editado'),items=[(self.product.pk,D('3'))])
        with self.assertRaises(ValidationError):confirm(actor=self.operator,sale_id=sale.pk,revision=1)
        with self.assertRaises(ValidationError):save_draft(actor=self.operator,key=sale.key,sale_id=sale.pk,revision=1,data=self.data(),items=[(self.product.pk,D('2'))])
        confirm(actor=self.operator,sale_id=sale.pk,revision=2)
        with self.assertRaises(ValidationError):save_draft(actor=self.operator,key=sale.key,sale_id=sale.pk,revision=3,data=self.data(),items=[(self.product.pk,D('2'))])
    def test_tax_override_requires_reason_and_is_audited(self):
        with self.assertRaises(ValidationError):self.draft(tax_override=D('0'))
        sale=self.confirmed(tax_override=D('0'),tax_reason='Isenção teste',tax_rule=None)
        self.assertEqual(sale.tax_amount,0);self.assertTrue(sale.tax_snapshot['override'])
        self.assertEqual(AuditLog.objects.get(entity='sales.Sale',entity_id=str(sale.pk),operation='confirm_sale').after['tax']['reason'],'Isenção teste')
    def test_tax_base_and_validity(self):
        self.rule.base='PRODUCTS';self.rule.save();sale=self.confirmed();self.assertEqual(sale.tax_amount,D('4.50'))
        self.rule.ends_on=self.company.cutover_date-timedelta(days=1);self.rule.starts_on=self.rule.ends_on;self.rule.save()
        with self.assertRaises(ValidationError):self.draft(invoice_number='200')
    def test_no_implicit_tax_rate(self):
        with self.assertRaises(ValidationError):self.draft(tax_rule=None)
    def test_zero_revenue_negative_margin(self):
        sale=self.confirmed(products_amount=D('0'),discount=D('0'),shipping_received=D('0'))
        self.assertIsNone(sale.margin_percent);self.assertEqual(sale.margin_label,'MARGEM NEGATIVA')
    def test_margin_threshold_snapshot(self):
        sale=self.confirmed(products_amount=D('30'),discount=D('0'),shipping_received=D('0'))
        self.assertEqual(sale.margin_label,'ALERTA');self.company.minimum_margin=0;self.company.save();sale.refresh_from_db();self.assertEqual(sale.minimum_margin,10)
    def test_invalid_money_date_quantity(self):
        for changes in [{'products_amount':D('-1')},{'fees':D('1.001')},{'discount':D('101')},{'date':self.company.cutover_date-timedelta(days=1)},{'date':timezone.localdate()+timedelta(days=1)}]:
            with self.assertRaises(ValidationError):self.draft(**changes)
        for quantity in [D('0'),D('-1'),D('0.00001'),D('NaN')]:
            with self.assertRaises(ValidationError):self.draft(items=[(self.product.pk,quantity)])
    def test_inactive_after_draft_blocked(self):
        sale=self.draft();self.channel.active=False;self.channel.save()
        with self.assertRaises(ValidationError):confirm(actor=self.operator,sale_id=sale.pk,revision=1)
    def test_permissions_html_api_and_service(self):
        sale=self.confirmed();self.client.force_login(self.operator)
        result=self.client.get(reverse('sale_detail',args=[sale.pk]));self.assertEqual(result.status_code,200)
        self.assertNotContains(result,'CMV histórico');self.assertNotContains(result,'Margem de contribuição')
        self.assertEqual(self.client.get(reverse('sale_result',args=[sale.pk])).status_code,403)
        self.assertEqual(self.client.get(reverse('sales_configuration',args=['canais'])).status_code,403)
        unrelated=User.objects.create_user('no-permission')
        with self.assertRaises(PermissionDenied):cancel(actor=unrelated,sale_id=sale.pk,reason='Teste')
        self.client.force_login(unrelated);self.assertEqual(self.client.get(reverse('sales')).status_code,403)
        self.client.force_login(self.actor);self.assertEqual(self.client.get(reverse('sale_result',args=[sale.pk])).json()['cmv'],'10.000000')
    def test_configuration_and_inactivation_audited(self):
        with self.assertRaises(PermissionDenied):save_configuration(actor=self.operator,model=SalesChannel,data={'name':'X','active':True})
        save_configuration(actor=self.actor,model=SalesChannel,pk=self.channel.pk,data={'name':'Novo nome','active':False})
        self.channel.refresh_from_db();self.assertFalse(self.channel.active)
        self.assertTrue(AuditLog.objects.filter(operation='sales_configuration').exists())
    def test_pages_filters_and_post_only(self):
        sale=self.draft();self.client.force_login(self.actor)
        for url in ['sales','sale_new']:
            self.assertEqual(self.client.get(reverse(url)).status_code,200)
        for kind in ['canais','impostos']:self.assertEqual(self.client.get(reverse('sales_configuration',args=[kind])).status_code,200)
        self.assertContains(self.client.get(reverse('sales'),{'q':'TEST-1'}),'100')
        self.assertNotContains(self.client.get(reverse('sales'),{'status':'CONFIRMED'}),'href="/vendas/1/"')
        self.assertEqual(self.client.get(reverse('sale_confirm',args=[sale.pk])).status_code,405)
    def test_csrf_enforced(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True);client.force_login(self.actor);sale=self.draft()
        self.assertEqual(client.post(reverse('sale_confirm',args=[sale.pk]),{'revision':1}).status_code,403)

@skipUnless(connection.vendor=='postgresql','PostgreSQL concurrency')
class SalesConcurrency(Fixture,TransactionTestCase):
    def test_concurrent_confirmations_last_units(self):
        first=self.draft(items=[(self.product.pk,D('10'))]);second=self.draft(items=[(self.product.pk,D('10'))],invoice_number='200')
        def worker(pk):
            close_old_connections()
            try:
                actor=User.objects.get(pk=self.operator.pk)
                confirm(actor=actor,sale_id=pk,revision=1);return 'ok'
            except ValidationError:return 'shortage'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,[first.pk,second.pk]))
        self.assertCountEqual(results,['ok','shortage']);self.product.refresh_from_db();self.assertEqual(self.product.quantity,0)
    def test_concurrent_same_sale_is_idempotent(self):
        sale=self.draft()
        def worker(_):
            close_old_connections()
            try:return confirm(actor=User.objects.get(pk=self.operator.pk),sale_id=sale.pk,revision=1).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(list(pool.map(worker,[1,2])),[sale.pk,sale.pk])
        self.assertEqual(StockOperation.objects.filter(kind='SALE_OUT').count(),1)

@skipUnless(connection.vendor=='postgresql','PostgreSQL history triggers')
class SalesHistory(Fixture,TestCase):
    def test_database_rejects_historical_mutation(self):
        sale=self.confirmed()
        for mutate in [lambda:Sale.objects.filter(pk=sale.pk).update(cmv=0),lambda:SaleItem.objects.filter(sale=sale).update(quantity=100),lambda:SaleItem.objects.create(sale=sale,product=self.product,quantity=1),lambda:SaleConsumption.objects.all().update(item_id=sale.items.get().pk)]:
            with self.assertRaises(DatabaseError),transaction.atomic():mutate()
        cancel(actor=self.actor,sale_id=sale.pk,reason='Permitido')
        with self.assertRaises(DatabaseError),transaction.atomic():Sale.objects.filter(pk=sale.pk).update(status='DRAFT')
