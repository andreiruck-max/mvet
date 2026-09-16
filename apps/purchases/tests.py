from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal as D
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth.models import User, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, connections, close_old_connections, DatabaseError, transaction
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.core.models import Company, AuditLog
from apps.products.models import Product
from apps.inventory.models import StockLocation, StockMovement, StockOperation
from apps.inventory.services import execute, reverse as reverse_stock
from apps.sales.models import SalesChannel, TaxRule
from apps.sales.services import save_draft as sale_draft, confirm as confirm_sale
from .models import Supplier, Purchase, PurchaseItem, PurchaseInstallment
from .services import save_supplier, save_draft, confirm, receive, cancel, allocation
from .selectors import supplier_report, purchases

class Fixture:
    def setUp(self):
        self.company=Company.objects.create(pk=1)
        self.admin=User.objects.create_superuser('purchase-owner')
        self.buyer=User.objects.create_user('buyer');self.buyer.user_permissions.add(Permission.objects.get(codename='operate_purchases'))
        self.seller=User.objects.create_user('seller');self.seller.user_permissions.add(Permission.objects.get(codename='operate_sales'))
        self.supplier=Supplier.objects.create(legal_name='Fornecedor teste')
        self.location=StockLocation.objects.create(name='Mercadovet teste')
        self.product=Product.objects.create(sku='BUY-01',name='Produto de compra')
        self.date=timezone.localdate()
    def data(self,**changes):
        data={'supplier':self.supplier,'document':'100','series':'','date':self.date,'location':self.location,'discount':D('0'),'freight':D('0'),'other_costs':D('0'),'notes':''};data.update(changes);return data
    def draft(self,items=None,installments=None,**changes):
        return save_draft(actor=self.buyer,key=uuid4(),data=self.data(**changes),items=items or [(self.product.pk,D('10'),D('5'))],installments=installments if installments is not None else [(self.date,D('50'),'')])
    def ordered(self,**changes):
        p=self.draft(**changes);return confirm(actor=self.buyer,purchase_id=p.pk,revision=p.revision)
    def received(self,**changes):
        p=self.ordered(**changes);return receive(actor=self.buyer,purchase_id=p.pk,date=self.date,revision=p.revision)

class PurchasesTests(Fixture,TestCase):
    def test_draft_order_and_receipt_are_separate(self):
        p=self.draft();self.assertEqual(self.product.balances.count(),0)
        p=confirm(actor=self.buyer,purchase_id=p.pk,revision=p.revision);self.assertEqual(p.status,'ORDERED');self.assertFalse(StockMovement.objects.exists())
        p=receive(actor=self.buyer,purchase_id=p.pk,date=self.date,revision=p.revision)
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,10);self.assertEqual(self.product.value,50);self.assertEqual(self.product.average_cost,5);self.assertEqual(p.status,'RECEIVED')
    def test_weighted_average_and_current_location(self):
        execute(actor=self.admin,key=uuid4(),kind='OPENING',date=self.company.cutover_date,reason='Inicial',product_id=self.product.pk,location_id=self.location.pk,quantity=D('10'),cost=D('10'))
        full=StockLocation.objects.create(name='Full');self.received(location=full)
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,20);self.assertEqual(self.product.average_cost,D('7.5'));self.assertEqual(self.product.balances.get(location=full).quantity,10)
    def test_largest_remainder_conserves_total(self):
        self.assertEqual(allocation([D('1'),D('1'),D('1')],D('1.00')),[D('.34'),D('.33'),D('.33')])
        self.assertEqual(allocation([D('0'),D('1')],D('1.01')),[D('0'),D('1.01')])
        for total in [D('0'),D('.01'),D('3.47'),D('100.01')]:self.assertEqual(sum(allocation([D('1'),D('3'),D('7')],total)),total)
    def test_discount_freight_other_costs_and_multiple_items(self):
        other=Product.objects.create(sku='BUY-02',name='Segundo')
        p=self.received(items=[(self.product.pk,D('2'),D('10')),(other.pk,D('3'),D('20'))],discount=D('5'),freight=D('10'),other_costs=D('3'),installments=[(self.date,D('44'),''),(self.date+timedelta(days=30),D('44'),'')])
        self.assertEqual(p.products_total,80);self.assertEqual(p.total,88)
        self.assertEqual(list(p.items.values_list('allocated_total',flat=True)),[D('22'),D('66')])
        self.assertEqual(sum(p.receipt.movements.values_list('value',flat=True)),88)
    def test_fractional_quantities_and_cent_rounding(self):
        p=self.received(items=[(self.product.pk,D('.3333'),D('1.234567'))],installments=[(self.date,D('.41'),'')])
        self.product.refresh_from_db();self.assertEqual(p.total,D('.41'));self.assertEqual(self.product.quantity,D('.3333'));self.assertEqual(self.product.value,D('.41'))
    def test_duplicate_product_lines_receive_and_reverse(self):
        p=self.received(items=[(self.product.pk,D('2'),D('5')),(self.product.pk,D('4'),D('10'))])
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,6);self.assertEqual(self.product.value,50)
        cancel(actor=self.buyer,purchase_id=p.pk,reason='Duplicado');self.product.refresh_from_db();self.assertEqual(self.product.quantity,0);self.assertEqual(self.product.value,0)
    def test_installments_do_not_duplicate_purchase_totals(self):
        self.received(installments=[(self.date,D('25'),''),(self.date+timedelta(days=30),D('25'),'')])
        summary,_,outstanding=supplier_report(self.supplier)
        self.assertEqual(summary['total'],50);self.assertEqual(summary['count'],1);self.assertEqual(summary['average'],50);self.assertEqual(outstanding.count(),2)
    def test_draft_without_installments_can_be_completed_later(self):
        p=self.draft(installments=[])
        with self.assertRaises(ValidationError):confirm(actor=self.buyer,purchase_id=p.pk,revision=1)
        p=save_draft(actor=self.buyer,purchase_id=p.pk,key=p.key,revision=1,data=self.data(),items=[(self.product.pk,D('10'),D('5'))],installments=[(self.date,D('50'),'')]);confirm(actor=self.buyer,purchase_id=p.pk,revision=2)
    def test_schedule_mismatch_and_invalid_amounts_dates(self):
        for installments in [[(self.date,D('49'),'')],[(self.date,D('0'),'')],[(self.date-timedelta(days=1),D('50'),'')]]:
            with self.assertRaises(ValidationError):self.draft(installments=installments)
        for changes in [{'discount':D('51')},{'freight':D('-1')},{'other_costs':D('.001')},{'date':self.company.cutover_date-timedelta(days=1)}]:
            with self.assertRaises(ValidationError):self.draft(**changes)
    def test_zero_cost_gift_and_invalid_zero_basis_rateio(self):
        p=self.received(items=[(self.product.pk,D('1'),D('0'))],installments=[]);self.assertEqual(p.total,0)
        with self.assertRaises(ValidationError):self.draft(document='200',items=[(self.product.pk,D('1'),D('0'))],freight=D('1'),installments=[])
    def test_kit_is_not_receivable(self):
        kit=Product.objects.create(sku='KIT',name='Kit',kind='KIT')
        with self.assertRaises(ValidationError):self.draft(items=[(kit.pk,D('1'),D('50'))])
    def test_idempotent_create_confirm_receive_cancel(self):
        key=uuid4();kwargs=dict(actor=self.buyer,key=key,data=self.data(),items=[(self.product.pk,D('10'),D('5'))],installments=[(self.date,D('50'),'')])
        p=save_draft(**kwargs);self.assertEqual(save_draft(**kwargs).pk,p.pk)
        with self.assertRaises(ValidationError):save_draft(**{**kwargs,'data':self.data(notes='Mudou')})
        confirm(actor=self.buyer,purchase_id=p.pk,revision=1);confirm(actor=self.buyer,purchase_id=p.pk,revision=1)
        receive(actor=self.buyer,purchase_id=p.pk,date=self.date,revision=2);receive(actor=self.buyer,purchase_id=p.pk,date=self.date,revision=2)
        cancel(actor=self.buyer,purchase_id=p.pk,reason='Teste');cancel(actor=self.buyer,purchase_id=p.pk,reason='Teste')
        self.assertEqual(StockOperation.objects.count(),2)
    def test_cancel_order_cancels_only_obligations(self):
        p=self.ordered();cancel(actor=self.buyer,purchase_id=p.pk,reason='Desistência')
        self.assertEqual(p.installments.get().status,'CANCELLED');self.assertFalse(StockMovement.objects.exists())
    def test_cancel_receipt_restores_average_and_all_installments(self):
        execute(actor=self.admin,key=uuid4(),kind='OPENING',date=self.company.cutover_date,reason='Inicial',product_id=self.product.pk,location_id=self.location.pk,quantity=D('3'),cost=D('9'))
        p=self.received();cancel(actor=self.buyer,purchase_id=p.pk,reason='Documento incorreto')
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,3);self.assertEqual(self.product.value,27);self.assertEqual(self.product.average_cost,9)
    def test_cancel_after_later_movement_rejected(self):
        p=self.received();execute(actor=self.admin,key=uuid4(),kind='ISSUE',date=self.date,reason='Saída',product_id=self.product.pk,location_id=self.location.pk,quantity=D('1'))
        with self.assertRaises(ValidationError):cancel(actor=self.buyer,purchase_id=p.pk,reason='Erro')
        p.refresh_from_db();self.assertEqual(p.status,'RECEIVED');self.assertEqual(p.installments.get().status,'PENDING')
    def test_purchase_receipt_then_transfer_to_full_and_reverse(self):
        p=self.received();full=StockLocation.objects.create(name='Estoque Full')
        transfer=execute(actor=self.admin,key=uuid4(),kind='TRANSFER',date=self.date,reason='Reposição Full',product_id=self.product.pk,location_id=self.location.pk,target_location_id=full.pk,quantity=D('4'))
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,10);self.assertEqual(self.product.value,50);self.assertEqual(self.product.average_cost,5)
        self.assertEqual(self.product.balances.get(location=self.location).quantity,6);self.assertEqual(self.product.balances.get(location=full).quantity,4)
        with self.assertRaises(ValidationError):cancel(actor=self.buyer,purchase_id=p.pk,reason='Há transferência')
        reverse_stock(actor=self.admin,operation_id=transfer.pk,key=uuid4(),date=self.date,reason='Retorno antes de cancelar')
        cancel(actor=self.buyer,purchase_id=p.pk,reason='Compra incorreta')
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,0);self.assertEqual(self.product.value,0)

    def test_generic_inventory_reversal_is_blocked(self):
        p=self.received()
        with self.assertRaises(ValidationError):reverse_stock(actor=self.admin,operation_id=p.receipt_id,key=uuid4(),date=self.date,reason='Bypass')
    def test_confirmed_edit_and_stale_revision_rejected(self):
        p=self.draft()
        with self.assertRaises(ValidationError):confirm(actor=self.buyer,purchase_id=p.pk,revision=0)
        confirm(actor=self.buyer,purchase_id=p.pk,revision=1)
        with self.assertRaises(ValidationError):save_draft(actor=self.buyer,key=p.key,purchase_id=p.pk,revision=2,data=self.data(),items=[(self.product.pk,D('1'),D('50'))],installments=[(self.date,D('50'),'')])
    def test_duplicate_supplier_document_series(self):
        self.draft(document='00100',series='01')
        with self.assertRaises(ValidationError):self.draft(document='100',series='1')
        self.draft(document='100',series='2')
        another=Supplier.objects.create(legal_name='Outro');self.draft(supplier=another,document='100',series='1')
    def test_receipt_failure_rolls_back_inventory_and_state(self):
        p=self.ordered()
        with patch('apps.purchases.services.audit',side_effect=RuntimeError('Falha sintética')):
            with self.assertRaises(RuntimeError):receive(actor=self.buyer,purchase_id=p.pk,date=self.date,revision=2)
        p.refresh_from_db();self.product.refresh_from_db();self.assertEqual(p.status,'ORDERED');self.assertEqual(self.product.quantity,0);self.assertFalse(StockMovement.objects.exists());self.assertIsNone(p.items.get().movement_id)
    def test_inactive_supplier_location_or_product_blocked(self):
        p=self.ordered();self.product.active=False;self.product.save(update_fields=['active'])
        with self.assertRaises(ValidationError):receive(actor=self.buyer,purchase_id=p.pk,date=self.date,revision=2)
        self.supplier.active=False;self.supplier.save()
        with self.assertRaises(ValidationError):self.draft(document='200')
    def test_backdated_receipt_cannot_rewrite_later_inventory(self):
        p=self.ordered(date=self.company.cutover_date)
        execute(actor=self.admin,key=uuid4(),kind='RECEIPT',date=self.date,reason='Atual',product_id=self.product.pk,location_id=self.location.pk,quantity=D('1'),cost=D('1'))
        with self.assertRaises(ValidationError):receive(actor=self.buyer,purchase_id=p.pk,date=self.company.cutover_date,revision=2)
    def test_historical_sales_cmv_does_not_change(self):
        self.received()
        channel=SalesChannel.objects.create(name='Teste');rule=TaxRule.objects.create(name='Teste',rate=D('0'),starts_on=self.company.cutover_date,base='REVENUE')
        data={name:D('0') for name in ['discount','shipping_received','shipping_paid','fees','difal','commission','other_costs']}
        data.update(date=self.date,invoice_number='S1',invoice_series='',channel=channel,location=self.location,products_amount=D('10'),tax_rule=rule,tax_override=None,tax_reason='',notes='')
        sale=sale_draft(actor=self.seller,key=uuid4(),data=data,items=[(self.product.pk,D('1'))]);sale=confirm_sale(actor=self.seller,sale_id=sale.pk,revision=1)
        self.received(document='200',items=[(self.product.pk,D('10'),D('20'))],installments=[(self.date,D('200'),'')])
        sale.refresh_from_db();self.assertEqual(sale.cmv,5)
    def test_supplier_normalization_and_inactivation(self):
        supplier=save_supplier(actor=self.buyer,data={'legal_name':'Empresa','document':'12.345.678/0001-90','active':True})
        self.assertEqual(supplier.document,'12345678000190')
        with self.assertRaises(ValidationError):save_supplier(actor=self.buyer,data={'legal_name':'Duplicado','document':'12345678000190'})
        save_supplier(actor=self.buyer,pk=supplier.pk,data={'active':False});supplier.refresh_from_db();self.assertFalse(supplier.active)
    def test_filters_due_dates_are_same_installment_and_no_duplicates(self):
        today=self.date;p=self.ordered(installments=[(today,D('25'),''),(today+timedelta(days=30),D('25'),'')])
        self.assertEqual(purchases({'due_start':today+timedelta(days=1),'due_end':today+timedelta(days=29)}).count(),0)
        self.assertEqual(purchases({'q':'BUY-01','pending':'pending'}).count(),1)
        self.assertEqual(purchases({'location':self.location}).count(),1)
    def test_permissions_are_separate_from_sales_and_reports(self):
        p=self.draft();self.client.force_login(self.seller)
        for name,args in [('purchases',[]),('purchase_detail',[p.pk]),('suppliers',[]),('supplier_summary',[self.supplier.pk])]:self.assertEqual(self.client.get(reverse(name,args=args)).status_code,403)
        with self.assertRaises(PermissionDenied):receive(actor=self.seller,purchase_id=p.pk,date=self.date,revision=1)
        self.client.force_login(self.buyer);self.assertNotContains(self.client.get(reverse('supplier_detail',args=[self.supplier.pk])),'Total comprado')
        self.assertEqual(self.client.get(reverse('supplier_summary',args=[self.supplier.pk])).status_code,403)
        self.assertEqual(self.client.get(reverse('product_lookup'),{'q':'BUY'}).status_code,200)
        self.assertNotIn('cost',self.client.get(reverse('product_lookup'),{'q':'BUY'}).json()['results'][0])
        self.client.force_login(self.admin);self.assertContains(self.client.get(reverse('supplier_detail',args=[self.supplier.pk])),'Total comprado')
    def test_pages_post_only_and_csrf(self):
        p=self.draft();self.client.force_login(self.buyer)
        for name,args in [('purchases',[]),('purchase_new',[]),('purchase_detail',[p.pk]),('supplier_new',[]),('suppliers',[]),('supplier_detail',[self.supplier.pk])]:self.assertEqual(self.client.get(reverse(name,args=args)).status_code,200)
        self.assertEqual(self.client.get(reverse('purchase_receive',args=[p.pk])).status_code,405)
        client=Client(enforce_csrf_checks=True);client.force_login(self.buyer)
        self.assertEqual(client.post(reverse('purchase_confirm',args=[p.pk]),{'revision':1}).status_code,403)

@skipUnless(connection.vendor=='postgresql','PostgreSQL tests')
class PostgreSQLPurchases(Fixture,TransactionTestCase):
    def test_simultaneous_receipts_are_idempotent(self):
        p=self.ordered()
        def worker(_):
            close_old_connections()
            try:return receive(actor=User.objects.get(pk=self.buyer.pk),purchase_id=p.pk,date=self.date,revision=2).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(list(pool.map(worker,[1,2])),[p.pk,p.pk])
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,10);self.assertEqual(StockOperation.objects.filter(kind='PUR_RECEIPT').count(),1)
    def test_database_blocks_history_mutations(self):
        p=self.received()
        for mutate in [lambda:Purchase.objects.filter(pk=p.pk).update(total=0),lambda:PurchaseItem.objects.filter(purchase=p).update(unit_cost=0),lambda:PurchaseInstallment.objects.filter(purchase=p).update(amount=1),lambda:PurchaseItem.objects.create(purchase=p,product=self.product,quantity=1,unit_cost=1)]:
            with self.assertRaises(DatabaseError),transaction.atomic():mutate()
        cancel(actor=self.buyer,purchase_id=p.pk,reason='Legítimo')
        with self.assertRaises(DatabaseError),transaction.atomic():Purchase.objects.filter(pk=p.pk).update(status='DRAFT')
