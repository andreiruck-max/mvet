from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.finance.models import FinancialTitle
from apps.inventory.models import StockMovement
from apps.purchases import services as purchases
from apps.purchases.models import Purchase, Supplier
from .models import BlingConnection, PurchaseInvoiceImport
from . import purchase_services as services
from .test_purchase_import import incoming, SUPPLIER
from .test_xml_discounts import xml
from .tests import ISSUER, payload
from .xml_discounts import enrich

OTHER = '22222222000122'


def invoice_document(data, recipient, *, direction='1', issuer=SUPPLIER):
    identity = f'<ide><tpNF>{direction}</tpNF></ide><emit><CNPJ>{issuer}</CNPJ></emit><dest>{recipient}</dest>'
    return xml(data).replace(b'<det ', identity.encode() + b'<det ', 1)


def enriched(data, raw):
    with patch('apps.integrations.xml_discounts.build_opener') as network:
        network.return_value.open.return_value.__enter__.return_value.read.return_value = raw
        return enrich(dict(data, xml='https://www.bling.com.br/synthetic.xml'))


class BuyerEvidenceTests(SimpleTestCase):
    def test_binding_is_separate_from_discounts_and_not_accepted_from_unread_json(self):
        data = incoming(valorNota='93.52')
        raw = invoice_document(data, f'<CNPJ>{OTHER}</CNPJ>')
        incomplete = enriched(data, raw.replace(b'<vDesc>6.48</vDesc>',b'<vDesc>1.00</vDesc>',1))
        self.assertEqual(incomplete['_xml_buyer']['recipient'], OTHER)
        self.assertNotIn('_xml_discounts', incomplete)
        self.assertNotIn('_xml_buyer', enrich(dict(data, _xml_buyer={'recipient':ISSUER})))
        self.assertNotIn('_xml_buyer', enriched(data, raw.replace(b'Id="NFe4',b'Id="NFe5')))
        self.assertNotIn('_xml_buyer', enriched(payload(valorNota='93.52'), raw))

    def test_self_issued_entry_is_bought_by_issuer_not_counterparty(self):
        conn = SimpleNamespace(issuer=ISSUER, company=SimpleNamespace(cnpj=ISSUER))
        data = incoming(chaveAcesso=payload()['chaveAcesso'], valorNota='93.52')
        for direction, expected in [('0','MATCH'),('1','MISMATCH')]:
            with self.subTest(direction=direction):
                raw = invoice_document(data,f'<CNPJ>{SUPPLIER}</CNPJ>',direction=direction,issuer=ISSUER)
                self.assertEqual(services.buyer_check(enriched(data,raw)['_xml_buyer'],conn),expected)
        conn.company.cnpj = OTHER
        self.assertEqual(services.buyer_check(None,conn),'MISMATCH')

    def test_individual_recipient_and_issuer_inconsistent_with_the_key_block(self):
        conn = SimpleNamespace(issuer=ISSUER, company=SimpleNamespace(cnpj=None))
        data = incoming(valorNota='93.52')
        for recipient, issuer in [('<CPF>11111111111</CPF>',SUPPLIER), (f'<CNPJ>{ISSUER}</CNPJ>',OTHER)]:
            with self.subTest(recipient=recipient):
                raw = invoice_document(data,recipient,issuer=issuer)
                self.assertEqual(services.buyer_check(enriched(data,raw)['_xml_buyer'],conn),'MISMATCH')


class BuyerWorkflowTests(Fixture,TestCase):
    def setUp(self):
        super().setUp()
        self.conn = BlingConnection.objects.create(pk=1, issuer=ISSUER)
        self.supplier = Supplier.objects.create(legal_name='Fornecedor sintético',document=SUPPLIER)
        self.data = incoming()
        self.before = StockMovement.objects.count()

    def stage(self, buyer=None, **overrides):
        data = dict(self.data, **overrides)
        if buyer:
            data = enriched(data, invoice_document(data, f'<CNPJ>{buyer}</CNPJ>'))
        return services.stage(actor=self.actor,connection=self.conn,payload=data)

    def draft(self, row):
        return services.create_draft(actor=self.actor, invoice_id=row.pk, revision=row.revision,
            supplier=self.supplier,location=self.location,products=[self.product],discount=Decimal(0),
            freight=Decimal(0),other_costs=Decimal(0),reviewed=True,
            installments=[(timezone.localdate()+timedelta(days=30),Decimal('100'),'')])

    def test_mismatch_hides_commercial_fields_and_survives_refresh_without_xml(self):
        row = self.stage(OTHER)
        self.assertEqual((row.buyer_check,row.source),('MISMATCH',{}))
        self.assertEqual(self.stage().revision,row.revision)
        self.client.force_login(self.actor)
        for method in (self.client.get,self.client.post):
            page = method(reverse('bling_purchase_detail',args=[row.pk]))
            self.assertContains(page, services.BUYER_ERROR)
            self.assertNotContains(page,'Fornecedor sintético')
            self.assertNotContains(page, 'Importar rascunho de compra')
        with self.assertRaisesMessage(ValidationError, 'não identifica'):
            self.draft(row)
        self.assertFalse(Purchase.objects.exists())
        self.assertEqual(StockMovement.objects.count(),self.before)
        self.assertFalse(FinancialTitle.objects.exists())
        correct = self.stage(ISSUER)
        self.assertEqual(correct.buyer_check,'MATCH')
        self.assertGreater(correct.revision,row.revision)
        self.assertEqual(self.draft(correct).status,'DRAFT')

    def test_late_mismatch_blocks_recording_without_deleting_local_history(self):
        row = self.stage()
        p = self.draft(row)
        approved = PurchaseInvoiceImport.objects.get(pk=row.pk).approved_source
        changed = self.stage(OTHER, parcelas='invalid')
        self.assertTrue(changed.discrepancy)
        self.assertEqual(changed.approved_source,approved)
        with self.assertRaisesMessage(ValidationError,'não identifica'):
            purchases.confirm_and_receive(actor=self.actor,purchase_id=p.pk,date=timezone.localdate(),revision=p.revision)
        self.assertFalse(FinancialTitle.objects.exists())
        self.stage(ISSUER)
        order = purchases.confirm(actor=self.actor,purchase_id=p.pk,revision=p.revision)
        self.stage(OTHER)
        with self.assertRaisesMessage(ValidationError,'não identifica'):
            purchases.receive(actor=self.actor,purchase_id=p.pk,date=timezone.localdate(),revision=order.revision)
        self.assertEqual(FinancialTitle.objects.filter(purchase_installment__purchase=p).count(),1)
        self.assertEqual(StockMovement.objects.count(),self.before)
