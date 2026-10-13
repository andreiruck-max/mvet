from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from apps.sales.tests import Fixture
from .tests import payload, ISSUER
from .xml_discounts import extract, enrich, LIMIT
from .normalization import normalize
from .models import BlingConnection
from .services import stage
from .forms import ReviewForm


def xml(data, discount='6.48'):
    return f'''<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe><infNFe Id="NFe{data['chaveAcesso']}">
    <det nItem="1"><prod><cProd>TEST-1</cProd><qCom>2</qCom><vUnCom>50</vUnCom><vProd>100.00</vProd><vDesc>{discount}</vDesc></prod></det>
    <total><ICMSTot><vNF>93.52</vNF><vDesc>6.48</vDesc></ICMSTot></total></infNFe></NFe></nfeProc>'''.encode()


class XMLTests(SimpleTestCase):
    def test_explicit_discount_and_item_projection(self):
        data=payload(valorNota='93.52')
        data['_xml_discounts']=extract(xml(data),data)
        source=normalize(data,ISSUER)
        self.assertEqual(source['discount'],'6.48')
        self.assertEqual(source['items'][0]['discount'],'6.48')
        self.assertNotIn('xml',source)

    def test_no_inference_from_total_difference(self):
        self.assertNotIn('discount',normalize(payload(valorNota='93.52'),ISSUER))

    def test_mismatch_and_unsafe_documents_rejected(self):
        data=payload(valorNota='93.52')
        for raw in [xml(data,'3.24'),xml(data).replace(b'TEST-1',b'OTHER'),xml(data).replace(b'93.52',b'90.00'),xml(data).replace(b'NFe4',b'NFe5'),b'<!DOCTYPE x>'+xml(data),b'x'*(LIMIT+1),b'<broken>']:
            with self.subTest(raw=raw[:20]), self.assertRaises(ValidationError):extract(raw,data)

    @patch('apps.integrations.xml_discounts.build_opener')
    def test_download_does_not_forward_credentials_or_persist_url(self, opener):
        data=payload(valorNota='93.52',xml='https://www.bling.com.br/documento?token=synthetic')
        opener.return_value.open.return_value.__enter__.return_value.read.return_value=xml(data)
        result=enrich(data)
        request=opener.return_value.open.call_args.args[0]
        self.assertIsNone(request.get_header('Authorization'))
        self.assertEqual(result['_xml_discounts']['total'],'6.48')
        self.assertNotIn('xml',normalize(result,ISSUER))

    @patch('apps.integrations.xml_discounts.build_opener')
    def test_untrusted_urls_never_requested(self, opener):
        for link in ['http://www.bling.com.br/a','https://evil.test/a','https://www.bling.com.br.evil.test/a','https://user@www.bling.com.br/a','https://www.bling.com.br:8000/a']:
            with self.assertRaises(ValidationError):enrich(payload(xml=link))
        opener.assert_not_called()


class DiscountReviewTests(Fixture, TestCase):
    def test_discount_prefilled_and_manual_choice_preserved(self):
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        data=payload(valorNota='93.52')
        data['_xml_discounts']=extract(xml(data),data)
        row=stage(actor=self.actor,connection=connection,payload=data)
        self.assertEqual(ReviewForm(invoice=row,actor=self.actor).initial['discount'],Decimal('6.48'))
        row.review_overrides={'discount':'4.00'}
        self.assertEqual(ReviewForm(invoice=row,actor=self.actor).initial['discount'],'4.00')

    def test_sync_and_refresh_fill_pending_discount(self):
        from django.utils import timezone
        from . import bling
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER,tokens='synthetic')
        data=payload(valorNota='93.52',xml='https://www.bling.com.br/synthetic.xml')
        with patch('apps.integrations.bling.read',side_effect=[{'data':[{'id':1000}]},{'data':data}]), patch('apps.integrations.xml_discounts.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=xml(data)
            run=bling.sync_page(actor=self.actor,start=timezone.localdate(),end=timezone.localdate())
        self.assertEqual(run.errors,0)
        from .models import InvoiceImport
        row=InvoiceImport.objects.get()
        self.assertEqual(row.source['discount'],'6.48')
        with patch('apps.integrations.bling.read',return_value={'data':data}), patch('apps.integrations.xml_discounts.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=xml(data)
            refreshed=bling.refresh_invoice(actor=self.actor,invoice_id=row.pk)
        self.assertEqual(refreshed.revision,row.revision)

    def test_purchase_item_discount_is_not_duplicated_in_global_field(self):
        from django.urls import reverse
        from .test_purchase_import import incoming
        from .purchase_services import stage as purchase_stage
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        data=incoming(valorNota='93.52')
        data['_xml_discounts']=extract(xml(data),data)
        row=purchase_stage(actor=self.actor,connection=connection,payload=data)
        self.client.force_login(self.actor)
        response=self.client.get(reverse('bling_purchase_detail',args=[row.pk]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['form'].initial['discount'],0)
        self.assertEqual(response.context['items'].forms[0].initial['discount'],Decimal('6.48'))
