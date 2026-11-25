from decimal import Decimal as D
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from apps.core.models import Company
from apps.finance.models import FinancialTitle
from apps.integrations.models import BlingConnection, PurchaseInvoiceImport
from apps.inventory.models import StockMovement
from apps.reporting.datasets import build
from .models import Purchase, PurchaseItem, PurchaseInstallment
from .services import confirm, receive, save_draft
from .tests import Fixture


class PurchaseDocumentScopeTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        Company.objects.get_or_create(pk=2, defaults={'active':False})
        self.primary = self.draft()
        self.fields = dict(supplier=self.supplier, location=self.location, created_by=self.admin,
                           date=self.date, series=self.primary.series, document=self.primary.document)
        # Same supplier, document, series, token and SKU; different cost and installment.
        self.other = Purchase.objects.create(company_id=2, key=self.primary.key, **self.fields,
            products_total=D('987.65'), total=D('987.65'))
        self.private_name = 'Linha sintética exclusiva da Agro'
        PurchaseItem.objects.create(company_id=2, purchase=self.other, product=self.product, quantity=1,
            unit_cost=D('987.65'), subtotal=D('987.65'), allocated_total=D('987.65'),
            landed_unit_cost=D('987.65'), name_snapshot=self.private_name)
        self.term = PurchaseInstallment.objects.create(company_id=2, purchase=self.other, number=1,
                                                       due_date=self.date, amount=D('987.65'))
        self.client.force_login(self.admin)

    def test_document_and_request_are_unique_within_each_buyer(self):
        for owner in (1, 2):
            for key, doc, expected in [(uuid4(), self.primary.document, 'purchase_owner_document'),
                                       (self.primary.key, 'NOVA', 'purchase_owner_request_key')]:
                with self.subTest(owner=owner, constraint=expected):
                    with self.assertRaises(IntegrityError) as error, transaction.atomic():
                        Purchase.objects.create(company_id=owner,key=key,**dict(self.fields,document=doc))
                    self.assertEqual(error.exception.__cause__.diag.constraint_name, expected)

    def test_receiving_primary_leaves_the_other_draft_and_schedule_unchanged(self):
        order = confirm(actor=self.admin,purchase_id=self.primary.pk,revision=self.primary.revision)
        receive(actor=self.admin,purchase_id=order.pk,date=self.date,revision=order.revision)
        self.assertEqual(list(FinancialTitle.objects.values_list('company_id','amount')), [(1,50)])
        self.assertEqual(list(StockMovement.objects.values_list('company_id','quantity','value')),[(1,10,50)])
        self.other.refresh_from_db()
        self.assertEqual((self.other.status,self.other.receipt_id,self.other.total), ('DRAFT',None,D('987.65')))
        self.assertFalse(FinancialTitle.objects.filter(purchase_installment=self.term).exists())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Purchase.objects.filter(pk=self.other.pk).update(status='ORDERED')
        with self.assertRaises(PermissionDenied):
            save_draft(actor=self.admin,company_id=2,key=uuid4(),data=self.data(),items=[],installments=[])

    def test_pages_exports_and_actions_select_only_current_buyer(self):
        query = {'q':self.primary.document,'company':2}
        page = self.client.get(reverse('purchases'),query)
        self.assertEqual([p.pk for p in page.context['page']], [self.primary.pk])
        for view in ('purchase_detail','purchase_edit','purchase_confirm','purchase_receive','purchase_cancel'):
            call = self.client.get if view in ('purchase_detail','purchase_edit') else self.client.post
            with self.subTest(view=view):
                self.assertEqual(call(reverse(view,args=[self.other.pk]),query).status_code,404)
        for kind in ('purchases','payables'):
            data = build(kind,self.admin, {})
            self.assertNotIn(self.private_name,str(data.rows))
        response = self.client.get(reverse('report_export',args=['purchases','xlsx']), query)
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as book:
            sheets = ''.join(book.read(n).decode() for n in book.namelist() if n.startswith('xl/worksheets/'))
        self.assertIn(self.product.name,sheets)
        self.assertNotIn(self.private_name,sheets)
        self.assertNotIn('987.65',sheets)
        self.assertEqual(self.client.get(reverse('report_export',args=['purchases','pdf']),query).status_code,200)
        self.assertFalse(FinancialTitle.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_secondary_draft_cannot_be_linked_to_primary_connection_or_title(self):
        connection, _ = BlingConnection.objects.get_or_create(pk=1,defaults={'issuer':'00000000000000'})
        with self.assertRaisesMessage(IntegrityError, 'owners differ'), transaction.atomic():
            PurchaseInvoiceImport.objects.create(connection=connection,external_id='1',access_key='0'*44,
                number='100',series='1',issued_on=self.date,purchase=self.other)
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            FinancialTitle.objects.create(company_id=1,purchase_installment=self.term,direction='PAY',
                date=self.date,due_date=self.date,description='Teste',amount=10,actor=self.admin)
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'purchase_owner_title_fk')
        self.assertFalse(PurchaseInvoiceImport.objects.exists())
