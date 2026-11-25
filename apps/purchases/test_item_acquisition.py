from decimal import Decimal as D
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase
from apps.core.models import Company
from apps.finance.models import FinancialTitle, FinancialEntry
from apps.inventory.models import StockBalance
from apps.products.models import Product
from . import services
from .tests import Fixture


class PurchaseItemAcquisitionTests(Fixture,TestCase):
    def setUp(self):
        super().setUp()
        self.b = Product.objects.create(sku='B-FISCAL',name='Produto B')
        self.lines = [
            dict(product_id=self.product.pk,quantity=D(3),unit_cost=D(20),discount=D(4),ipi=D('3.70'),
                 invoice_st=D(2),st=D('11.15'),recoverable_tax=D(1),ncm='85437092',fiscal_components={'freight':'1.00'}),
            dict(product_id=self.b.pk,quantity=D(1),unit_cost=D(50),difal=D('7.02'))]
        self.data_args = self.data(freight=D(1))

    def save(self):
        return services.save_draft(actor=self.admin,key=uuid4(),data=self.data_args,items=self.lines,
                                   installments=[(self.date,D('112.70'),'')])

    def test_exact_assigned_line_moves_only_into_the_buyers_stock(self):
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        other = StockBalance.objects.create(company_id=2,location=self.location,product=self.product,quantity=8,value=800,average_cost=100)
        purchase = self.save()
        self.assertEqual((purchase.total,purchase.external_tax_total,purchase.acquisition_total),(D('112.70'),D('18.17'),D('129.87')))
        self.assertEqual(list(purchase.items.values_list('allocated_total','landed_unit_cost')),
                         [(D('72.85'),D('24.283333')),(D('57.02'),D('57.020000'))])
        services.confirm_and_receive(actor=self.admin,purchase_id=purchase.pk,revision=purchase.revision,date=self.date)
        purchase.refresh_from_db()
        self.assertEqual(list(purchase.receipt.movements.order_by('product_id').values_list('company_id','value')),
                         [(1,D('72.85')),(1,D('57.02'))])
        self.assertEqual(list(FinancialTitle.objects.values_list('company_id','amount')),[(1,D('112.70'))])
        self.assertFalse(FinancialEntry.objects.exists())
        other.refresh_from_db(); self.assertEqual((other.quantity,other.value,other.average_cost),(8,800,100))
        with self.assertRaises(DatabaseError),transaction.atomic():
            purchase.items.update(ipi=D(99))

    def test_fiscal_evidence_follows_original_line_across_reordering(self):
        p=self.save()
        a,b=list(p.items.all())
        first=dict(self.lines[0], original_line=a.pk, invoice_other_tax=D(0))
        # Form preserves immutable XML components server-side; the order is not an identifier.
        first.pop('fiscal_components')
        args=dict(actor=self.admin,key=uuid4(),purchase_id=p.pk,revision=p.revision,data=self.data_args,
                  installments=[(self.date,D('112.70'),'')])
        for invalid in ([self.lines[1]], [dict(first, original_line=b.pk),self.lines[1]],[dict(first,ipi=D(0)),self.lines[1]]):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                services.save_draft(**args,items=invalid)
        p=services.save_draft(**args,items=[dict(self.lines[1],original_line=b.pk),first])
        self.assertEqual(p.items.get(product=self.product).fiscal_components,{'freight':'1.00'})
        self.assertEqual(p.items.get(product=self.product).allocated_total,D('72.85'))

    def test_bonus_cannot_capitalize_external_tax_or_create_a_title(self):
        self.data_args.update(acquisition_kind='BONUS',freight=D(0))
        with self.assertRaises(ValidationError):
            services.save_draft(actor=self.admin,key=uuid4(),data=self.data_args,items=self.lines,installments=[])
        p=services.save_draft(actor=self.admin,key=uuid4(),data=self.data_args,
            items=[dict(product_id=self.product.pk,quantity=D(2),unit_cost=D(10),ipi=D(3))],installments=[])
        services.confirm_and_receive(actor=self.admin,purchase_id=p.pk,revision=p.revision,date=self.date)
        self.assertEqual((p.total,p.items.get().allocated_total),(0,0))
        self.assertFalse(FinancialTitle.objects.exists())
