from decimal import Decimal as D
from uuid import uuid4
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, connection, DatabaseError
from django.urls import reverse
from django.test import TestCase
from apps.sales.tests import Fixture
from django.utils import timezone
from apps.products.models import Product
from apps.inventory.models import StockMovement
from apps.finance.models import FinancialTitle
from apps.expenses.models import ChartOfAccount
from apps.purchases import services as purchases
from apps.purchases.models import Purchase
from apps.reporting.selectors import dre
from . import test_purchase_import as helpers
from .test_purchase_import import incoming
from . import purchase_services as s


class FlexiblePurchaseTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        from .models import BlingConnection
        from .tests import ISSUER
        from .test_purchase_import import SUPPLIER
        from apps.purchases.models import Supplier
        self.connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        self.supplier=Supplier.objects.create(legal_name='Fornecedor sintético',document=SUPPLIER)
    stage=helpers.PurchaseImportTests.stage
    draft=helpers.PurchaseImportTests.draft
    # Reuse fixture helpers without repeating its test methods.
    def report(self):return dre({'start':timezone.localdate(),'end':timezone.localdate()})
    def posted(self,p):
        p=purchases.confirm(actor=self.actor,purchase_id=p.pk,revision=p.revision)
        return purchases.receive(actor=self.actor,purchase_id=p.pk,date=timezone.localdate(),revision=p.revision)

    def test_mixed_invoice_preserves_full_payable_without_inflating_stock(self):
        data=incoming(valorNota='150',parcelas=[])
        data['itens'].append(dict(data['itens'][0],codigo='',descricao='Item pessoal',quantidade=1,valor=50))
        row=s.stage(actor=self.actor,connection=self.connection,payload=data)
        cat=ChartOfAccount.objects.create(code='80',name='Retirada pessoal',nature='EQUITY')
        p=self.draft(row,products=[self.product,None],treatments=[{},dict(mode='NONSTOCK',category=cat)],installments=[(timezone.localdate(),D('150'),'')])
        p=self.posted(p)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity,12);self.assertEqual(self.product.value,150)
        self.assertEqual(FinancialTitle.objects.get().amount,150)
        personal=p.items.get(moves_stock=False)
        self.assertIsNone(personal.product_id);self.assertIsNone(personal.movement_id)
        self.assertEqual(personal.allocated_total,0);self.assertEqual(personal.nonstock_total,50)
        self.assertEqual(self.report()['expenses']['OPERATING'],0)
        purchases.cancel(actor=self.actor,purchase_id=p.pk,reason='Desfazer teste')
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,10)
        self.assertEqual(FinancialTitle.objects.get().status,'CANCELLED')

    def test_financial_only_packaging_category_accrues_once_and_cancel_reverses(self):
        row=self.stage()
        cat=ChartOfAccount.objects.create(code='04',name='Embalagens',nature='OPERATING')
        before=StockMovement.objects.count()
        p=self.draft(row,products=[None],treatments=[dict(mode='NONSTOCK',category=cat)])
        self.assertEqual(self.report()['expenses']['OPERATING'],0)
        p=self.posted(p)
        self.assertIsNone(p.receipt_id);self.assertEqual(StockMovement.objects.count(),before)
        self.assertEqual(FinancialTitle.objects.count(),1);self.assertEqual(self.report()['expenses']['OPERATING'],100)
        self.assertEqual(FinancialTitle.objects.get().category,'OPERATING')
        cat.name='Outro nome';cat.save()
        self.assertIn('Embalagens',self.report()['groups'][0]['label'])
        purchases.cancel(actor=self.actor,purchase_id=p.pk,reason='Desfazer')
        self.assertEqual(self.report()['expenses']['OPERATING'],0)

    def test_bonus_adds_quantity_zero_value_no_payable_and_preserves_fiscal(self):
        data=incoming();data['itens'][0]['cfop']='5910'
        row=s.stage(actor=self.actor,connection=self.connection,payload=data)
        with self.assertRaises(ValidationError):self.draft(row)
        p=self.draft(row,acquisition_kind='BONUS',installments=[])
        self.assertEqual(p.products_total,100);self.assertEqual(p.total,0)
        p=self.posted(p);self.product.refresh_from_db()
        self.assertEqual(self.product.quantity,12);self.assertEqual(self.product.value,50)
        self.assertEqual(self.product.average_cost,D('4.166667'))
        self.assertFalse(FinancialTitle.objects.exists());self.assertFalse(p.installments.exists())
        row.refresh_from_db();self.assertEqual(row.approved_source['total'],'100.00')
        purchases.cancel(actor=self.actor,purchase_id=p.pk,reason='Desfazer')
        self.product.refresh_from_db();self.assertEqual(self.product.average_cost,5)

    def test_bonus_still_blocks_transfer_return_and_paid_costs(self):
        for cfop in ('5152','5411'):
            data=incoming();data['itens'][0]['cfop']=cfop
            row=s.stage(actor=self.actor,connection=self.connection,payload=data)
            with self.assertRaises(ValidationError):self.draft(row,acquisition_kind='BONUS',installments=[])
        data=incoming();data['itens'][0]['cfop']='5910'
        row=s.stage(actor=self.actor,connection=self.connection,payload=data)
        with self.assertRaises(ValidationError):self.draft(row,acquisition_kind='BONUS')
        with self.assertRaises(ValidationError):self.draft(row,acquisition_kind='BONUS',freight=D('1'),installments=[])

    def test_new_product_without_external_code_custom_name_and_atomic_rollback(self):
        data=incoming();data['itens'][0]['codigo']=''
        row=s.stage(actor=self.actor,connection=self.connection,payload=data)
        self.assertFalse(row.error)
        treatment=dict(mode='NEW',new_sku='NEW-001',new_name='Nome escolhido localmente',new_unit='UN')
        with self.assertRaises(ValidationError):self.draft(row,products=[None],treatments=[treatment],freight=D('1'),installments=[])
        self.assertFalse(Product.objects.filter(sku='NEW-001').exists())
        p=self.draft(row,products=[None],treatments=[treatment]);self.posted(p)
        product=Product.objects.get(sku='NEW-001');self.assertEqual(product.name,treatment['new_name'])
        self.assertEqual(product.quantity,2)
        self.assertEqual(self.draft(row,products=[None],treatments=[treatment]).pk,p.pk)
        self.assertEqual(Product.objects.filter(sku='NEW-001').count(),1)

    def test_new_product_and_nonstock_require_own_permissions(self):
        self.operator.user_permissions.add(Permission.objects.get(codename='operate_purchases'))
        row=self.stage()
        with self.assertRaises(PermissionDenied):self.draft(row,actor=self.operator,products=[None],treatments=[dict(mode='NEW',new_sku='X',new_name='X',new_unit='UN')])
        with self.assertRaises(PermissionDenied):self.draft(row,actor=self.operator,products=[None],treatments=[dict(mode='NONSTOCK')])
        self.assertFalse(Purchase.objects.exists())

    def test_nonstock_allocated_share_keeps_discount_and_freight_conservative(self):
        p=purchases.save_draft(actor=self.actor,key=uuid4(),data=dict(supplier=self.supplier,location=self.location,document='allocation',series='',date=timezone.localdate(),discount=D('1'),freight=D('3'),other_costs=D('0'),notes=''),
            items=[dict(product_id=self.product.pk,quantity=D('2'),unit_cost=D('10'),moves_stock=True),dict(product_id=None,name='Caixas',quantity=D('1'),unit_cost=D('20'),moves_stock=False)],installments=[])
        stock=p.items.get(moves_stock=True);other=p.items.get(moves_stock=False)
        self.assertEqual(stock.allocated_total,21);self.assertEqual(other.nonstock_total,21);self.assertEqual(p.total,42)

    def test_postgres_protects_new_history_fields(self):
        if connection.vendor!='postgresql':self.skipTest('PostgreSQL')
        p=self.posted(self.draft(self.stage()))
        for changes in ({'moves_stock':False},{'category_snapshot':{'nature':'OPERATING'}}):
            with self.assertRaises(DatabaseError),transaction.atomic():p.items.update(**changes)
        with self.assertRaises(DatabaseError),transaction.atomic():Purchase.objects.filter(pk=p.pk).update(acquisition_kind='BONUS')

    def test_item_discount_only_reduces_its_product_and_matches_payable(self):
        other=Product.objects.create(sku='PROMO',name='Produto promocional',unit='UN')
        data=incoming(valorNota='180',parcelas=[])
        data['itens'].append(dict(data['itens'][0],codigo='PROMO',quantidade=1,valor=100))
        row=s.stage(actor=self.actor,connection=self.connection,payload=data)
        p=self.draft(row,products=[self.product,other],treatments=[{},dict(discount=D('20'))],installments=[(timezone.localdate(),D('180'),'')])
        self.assertEqual(list(p.items.values_list('allocated_total',flat=True)),[D('100'),D('80')])
        self.assertEqual(p.item_discounts,D('20'))
        p=self.posted(p)
        self.product.refresh_from_db();other.refresh_from_db()
        self.assertEqual(self.product.value,D('150'));self.assertEqual(other.value,D('80'))
        self.assertEqual(FinancialTitle.objects.get().amount,D('180'))
        if connection.vendor=='postgresql':
            with self.assertRaises(DatabaseError),transaction.atomic():p.items.update(discount=0)

    def test_item_discount_limits_and_general_discount_use_net_base(self):
        row=self.stage()
        for discount in (D('-1'),D('100.01')):
            with self.assertRaises(ValidationError):self.draft(row,treatments=[dict(discount=discount)],installments=[])
        with self.assertRaises(ValidationError):self.draft(row,treatments=[dict(discount=D('99'))],discount=D('2'),installments=[])
        # Total still must reconcile with the fiscal document (no double deduction).
        with self.assertRaises(ValidationError):self.draft(row,treatments=[dict(discount=D('10'))],installments=[])
        self.assertFalse(Purchase.objects.exists())
        p=purchases.save_draft(actor=self.actor,key=uuid4(),data=dict(supplier=self.supplier,location=self.location,document='net',series='',date=timezone.localdate(),discount=D('1'),freight=D('3'),other_costs=D('0'),notes=''),
            items=[dict(product_id=self.product.pk,quantity=D('1'),unit_cost=D('20'),discount=D('10')),dict(product_id=None,name='Caixas',quantity=D('1'),unit_cost=D('10'),moves_stock=False)],installments=[])
        self.assertEqual(p.total,D('22'))
        self.assertEqual(p.items.get(moves_stock=True).allocated_total,D('11'))
        self.assertEqual(p.items.get(moves_stock=False).nonstock_total,D('11'))

    def test_supplier_created_with_draft_atomic_permissions_and_idempotence(self):
        from apps.purchases.models import Supplier
        document=self.supplier.document;self.supplier.delete()
        row=self.stage()
        self.assertNotIn('supplier_phone',row.source)
        self.assertNotIn('supplier_email',row.source)
        self.assertNotIn('supplier_trade_name',row.source)
        supplier_data=dict(legal_name='Fornecedor importado',document=document,phone='4500000000',email='teste@example.com')
        with self.assertRaises(ValidationError):self.draft(row,supplier=None,supplier_data=supplier_data,freight=D('1'),installments=[])
        self.assertFalse(Supplier.objects.exists())
        self.operator.user_permissions.add(Permission.objects.get(codename='operate_purchases'))
        from apps.accounts.models import AccessPolicy
        AccessPolicy.objects.create(user=self.operator,rules={'core.manage_suppliers':False})
        with self.assertRaises(PermissionDenied):self.draft(row,actor=self.operator,supplier=None,supplier_data=supplier_data)
        self.assertFalse(Supplier.objects.exists())
        p=self.draft(row,supplier=None,supplier_data=supplier_data)
        self.assertEqual(p.supplier.document,document);self.assertEqual(p.supplier.email,'teste@example.com')
        self.assertTrue(p.supplier.active)
        self.assertEqual(self.draft(row,supplier=None,supplier_data=supplier_data).pk,p.pk)
        self.assertEqual(Supplier.objects.count(),1)
