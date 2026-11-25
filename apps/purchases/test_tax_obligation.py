from decimal import Decimal as D
from uuid import uuid4
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from apps.accounts.company_context import CompanyScope
from apps.core.models import Company
from apps.finance import services as finance
from apps.finance.models import FinancialTitle,FinancialEntry
from apps.inventory.models import StockMovement
from .models import Purchase,PurchaseTaxObligation
from .services import create_tax_obligation,confirm,cancel
from .tests import Fixture


class TaxObligationTests(Fixture,TestCase):
    def setUp(self):
        super().setUp()
        self.p=self.draft(items=[dict(product_id=self.product.pk,quantity=D(10),unit_cost=D(5),st=D('12.11'),difal=D('2.37'))])
        self.args=dict(actor=self.admin,purchase_id=self.p.pk,kind='ST',counterparty='Fisco sintético',due_date=self.date)

    def test_separate_creditor_retry_and_group_guard(self):
        with self.assertRaises(ValidationError):create_tax_obligation(**self.args)
        order=confirm(actor=self.admin,purchase_id=self.p.pk,revision=self.p.revision)
        title=create_tax_obligation(**self.args)
        self.assertEqual(create_tax_obligation(**self.args).pk,title.pk)
        difal=create_tax_obligation(**dict(self.args,kind='DIFAL'))
        self.assertEqual((title.company_id,title.amount,difal.amount,title.category,title.direction),(1,D('12.11'),D('2.37'),'PRINCIPAL','PAY'))
        self.assertEqual(list(FinancialTitle.objects.filter(purchase_installment__purchase=order).values_list('amount',flat=True)),[50])
        self.assertIsNone(title.purchase_installment_id)
        self.assertFalse(FinancialEntry.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        with self.assertRaisesMessage(ValidationError,'obrigação fiscal'):
            cancel(actor=self.admin,purchase_id=order.pk,reason='Conferência')
        self.admin._mvet_company_scope=CompanyScope((1,),group=True)
        with self.assertRaises(PermissionDenied):create_tax_obligation(**self.args)
        del self.admin._mvet_company_scope
        finance.cancel_title(actor=self.admin,pk=title.pk,reason='Cancelada no fisco')
        finance.cancel_title(actor=self.admin,pk=difal.pk,reason='Cancelada no fisco')
        cancel(actor=self.admin,purchase_id=order.pk,reason='Conferência')
        self.assertEqual(FinancialTitle.objects.filter(status='CANCELLED').count(),3)

    def test_raw_links_cannot_cross_owner_change_history_or_reuse_supplier_title(self):
        self.p=confirm(actor=self.admin,purchase_id=self.p.pk,revision=self.p.revision)
        original=FinancialTitle.objects.get()
        with self.assertRaisesMessage(IntegrityError,'separate fiscal'),transaction.atomic():
            PurchaseTaxObligation.objects.create(company_id=1,purchase=self.p,kind='DIFAL',title=original)
        title=create_tax_obligation(**self.args)
        with self.assertRaisesMessage(IntegrityError,'immutable'),transaction.atomic():
            PurchaseTaxObligation.objects.filter(title=title).update(kind='DIFAL')
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        other=Purchase.objects.create(company_id=2,key=uuid4(),supplier=self.supplier,location=self.location,created_by=self.admin,
                                      date=self.date,document='OUTRO',series='1')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('purchase_tax_obligation',args=[other.pk])).status_code,404)
        extra=FinancialTitle.objects.create(company_id=1,source='purchase_tax',direction='PAY',category='PRINCIPAL',
                                            actor=self.admin,date=self.date,due_date=self.date,amount=5)
        with self.assertRaises(IntegrityError) as exc,transaction.atomic():
            PurchaseTaxObligation.objects.create(company_id=2,purchase=other,kind='ST',title=extra)
        self.assertEqual(exc.exception.__cause__.diag.constraint_name,'fiscal_title_owner_fk')
        self.assertFalse(FinancialEntry.objects.exists())

    def test_create_requires_financial_permission_not_just_purchase_access(self):
        confirm(actor=self.admin,purchase_id=self.p.pk,revision=self.p.revision)
        with self.assertRaises(PermissionDenied):create_tax_obligation(**dict(self.args,actor=self.seller))
        self.client.force_login(self.seller)
        self.assertEqual(self.client.post(reverse('purchase_tax_obligation',args=[self.p.pk]),{}).status_code,403)
        self.assertFalse(PurchaseTaxObligation.objects.exists())
