from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.purchases.models import Supplier, Purchase
from apps.purchases import services as purchases
from apps.finance.models import FinancialTitle, FinancialEntry
from apps.inventory.models import StockMovement
from .models import BlingConnection, PurchaseInvoiceImport
from .tests import payload, ISSUER
from . import purchase_services as s, bling

SUPPLIER = '98765432000199'

def incoming(**changes):
    data = payload(tipo=0, situacao=7, contato={'nome': 'Fornecedor sintético', 'numeroDocumento': SUPPLIER},
        chaveAcesso='412609'+SUPPLIER+'550010000001231000000019',
        parcelas=[{'data': str(timezone.localdate()+timedelta(days=30)), 'valor': '100.00'}])
    data.update(changes)
    return data

class PurchaseImportTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.connection=BlingConnection.objects.create(pk=1, issuer=ISSUER, tokens='synthetic')
        self.supplier=Supplier.objects.create(legal_name='Fornecedor sintético',document=SUPPLIER)
    def stage(self, **changes):
        return s.stage(actor=self.actor,connection=self.connection,payload=incoming(**changes))
    def draft(self, row, **changes):
        data=dict(actor=self.actor,invoice_id=row.pk,revision=row.revision,supplier=self.supplier,location=self.location,
            products=[self.product],discount=D('0'),freight=D('0'),other_costs=D('0'),
            installments=[(timezone.localdate()+timedelta(days=30),D('100'),'')],reviewed=True)
        data.update(changes);return s.create_draft(**data)
    def test_import_draft_then_commitment_then_receipt_no_payment(self):
        before=StockMovement.objects.count();row=self.stage();p=self.draft(row)
        self.assertEqual(p.status,'DRAFT');self.assertEqual(p.total,100)
        self.assertFalse(FinancialTitle.objects.exists());self.assertEqual(StockMovement.objects.count(),before)
        p=purchases.confirm(actor=self.actor,purchase_id=p.pk,revision=p.revision)
        self.assertEqual(FinancialTitle.objects.count(),1);self.assertFalse(FinancialEntry.objects.exists())
        purchases.receive(actor=self.actor,purchase_id=p.pk,date=timezone.localdate(),revision=p.revision)
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,12)
        self.assertEqual(self.product.value,D('150'))
    def test_idempotency_cancel_and_external_change_preserve_link(self):
        row=self.stage();p=self.draft(row);self.assertEqual(self.draft(row).pk,p.pk)
        purchases.cancel(actor=self.actor,purchase_id=p.pk,reason='Teste')
        updated=self.stage(situacao=2);self.assertTrue(updated.discrepancy)
        self.assertEqual(updated.purchase_id,p.pk);self.assertEqual(updated.approved_source['status'],'7')
        self.assertEqual(Purchase.objects.count(),1)
    def test_invalid_refresh_blocks_draft_and_does_not_erase_identity(self):
        row=self.stage();self.stage(chaveAcesso='bad');row.refresh_from_db()
        self.assertTrue(row.error)
        with self.assertRaises(ValidationError):self.draft(row)
        self.assertEqual(row.access_key,incoming()['chaveAcesso'])
    def test_wrong_supplier_unit_total_and_stale_revision_roll_back(self):
        row=self.stage();other=Supplier.objects.create(legal_name='Outro',document='11111111000191')
        for changes in [dict(supplier=other),dict(reviewed=False),dict(revision=99),dict(freight=D('1'),installments=[])]:
            with self.assertRaises(ValidationError):self.draft(row,**changes)
        self.product.unit='CX';self.product.save()
        with self.assertRaises(ValidationError):self.draft(row)
        self.assertFalse(Purchase.objects.exists())
    def test_transfer_return_and_output_are_blocked(self):
        for cfop in ['5152','5411','5910']:
            data=incoming();data['itens'][0]['cfop']=cfop
            obj=s.stage(actor=self.actor,connection=self.connection,payload=data)
            self.assertTrue(obj.error)
        self.assertTrue(self.stage(tipo=1).error)
    def test_documented_input_query_and_sale_queue_isolation(self):
        with patch('apps.integrations.bling.read', side_effect=[{'data':[{'id':1000}]},{'data':incoming()}]) as remote:
            run=bling.sync_page(actor=self.actor,start=timezone.localdate(),end=timezone.localdate(),kind='PURCHASE',source_status=7)
        self.assertEqual(run.kind,'PURCHASE');self.assertEqual(run.processed,1)
        self.assertIn('tipo=0',remote.call_args_list[0].args[0])
        self.assertEqual(PurchaseInvoiceImport.objects.count(),1)
    def test_permissions_and_http_draft(self):
        row=self.stage();self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('bling_purchase_detail',args=[row.pk])).status_code,403)
        with self.assertRaises(PermissionDenied):self.draft(row,actor=self.operator)
        self.client.force_login(self.actor)
        response=self.client.post(reverse('bling_purchase_detail',args=[row.pk]),{
            'revision':row.revision,'supplier':self.supplier.pk,'location':self.location.pk,'discount':'0,00','freight':'0,00','other_costs':'0,00','reviewed':'on',
            'products-TOTAL_FORMS':1,'products-INITIAL_FORMS':1,'products-0-product':self.product.pk,
            'installments-TOTAL_FORMS':1,'installments-INITIAL_FORMS':1,'installments-0-due_date':str(timezone.localdate()+timedelta(days=30)), 'installments-0-amount':'100.00','installments-0-notes':''})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Purchase.objects.count(),1)
        self.assertFalse(FinancialTitle.objects.exists())
    def test_new_invalid_document_reported_by_external_id(self):
        with patch('apps.integrations.bling.read',side_effect=[{'data':[{'id':1000}]},{'data':incoming(chaveAcesso='bad')} ]):
            run=bling.sync_page(actor=self.actor,start=timezone.localdate(),end=timezone.localdate(),kind='PURCHASE',source_status=7)
        self.assertEqual(run.error_ids,['1000']);self.assertFalse(Purchase.objects.exists())

    def test_immutable_purchase_reference_in_postgres(self):
        from django.db import connection, transaction, DatabaseError
        if connection.vendor != 'postgresql': self.skipTest('PostgreSQL trigger')
        row=self.stage();self.draft(row)
        for changes in [{'purchase':None},{'approved_source':{}},{'external_id':'2000'}]:
            with self.assertRaises(DatabaseError),transaction.atomic():
                PurchaseInvoiceImport.objects.filter(pk=row.pk).update(**changes)
