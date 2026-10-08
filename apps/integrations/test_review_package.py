from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.sales.forms import SaleForm
from apps.sales.models import TaxRule
from .tests import payload, ISSUER
from .models import BlingConnection, InvoiceImport
from .services import stage, approve
from .forms import ReviewForm
from . import bulk


class ReviewPackageTests(Fixture,TestCase):
    def setUp(self):
        super().setUp()
        self.connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)

    def test_display_customer_is_allowlisted_and_refresh_does_not_flag_sale(self):
        row=stage(actor=self.actor,connection=self.connection,payload=payload())
        sale=approve(actor=self.actor,invoice_id=row.pk,revision=row.revision,data=self.data(),extra_costs=[],reviewed=True)
        contact={'nome':'Cliente sintético <script>','numeroDocumento':'PRIVATE-DOCUMENT','endereco':{'rua':'PRIVATE-ADDRESS'}}
        row=stage(actor=self.actor,connection=self.connection,payload=payload(contato=contact))
        self.assertEqual(row.source['customer_name'],contact['nome']);self.assertFalse(row.discrepancy)
        self.assertNotIn('PRIVATE',str(row.source));self.assertEqual(row.sale_id,sale.pk)
        self.client.force_login(self.actor)
        response=self.client.get(reverse('bling_queue'),{'status':''})
        self.assertContains(response,'Cliente sintético &lt;script&gt;');self.assertContains(response,'R$ 100,00')
        row=stage(actor=self.actor,connection=self.connection,payload=payload(contato=contact,valorNota='101'))
        self.assertTrue(row.discrepancy)

    def test_series_numeric_order_and_bulk_scope(self):
        for index,(series,number) in enumerate([('2','10'),('1','100'),('1','9'),('2','2')]):
            InvoiceImport.objects.create(connection=self.connection,external_id=str(index),series=series,number=number,fingerprint='test')
        self.assertEqual(list(bulk.filtered_rows('SALE',{}).values_list('series','number')),[('1','9'),('1','100'),('2','2'),('2','10')])
        self.client.force_login(self.actor)
        response=self.client.get(reverse('bling_queue'),{'series':'2'})
        self.assertEqual([r.number for r in response.context['page']],['2','10'])
        pairs=bulk.decode(self.actor,'SALE',response.context['bulk_all'])
        self.assertEqual(set(InvoiceImport.objects.filter(pk__in=[p[0] for p in pairs]).values_list('series',flat=True)),{'2'})

    def test_current_tax_default_invoice_date_and_manual_choice(self):
        today=timezone.localdate()
        recent=TaxRule.objects.create(name='Vigente recente',rate=Decimal('7'),starts_on=today,base='REVENUE')
        TaxRule.objects.create(name='Futura',rate=Decimal('9'),starts_on=today+timedelta(days=1),base='REVENUE')
        TaxRule.objects.create(name='Inativa',rate=Decimal('9'),starts_on=today,base='REVENUE',active=False)
        self.assertEqual(SaleForm(actor=self.actor)['tax_rule'].value(),recent.pk)
        row=stage(actor=self.actor,connection=self.connection,payload=payload())
        self.assertEqual(ReviewForm(invoice=row,actor=self.actor)['tax_rule'].value(),recent.pk)
        self.assertEqual(ReviewForm({'tax_rule':str(self.rule.pk)},invoice=row,actor=self.actor)['tax_rule'].value(),str(self.rule.pk))
        row.issued_on=self.company.cutover_date
        self.assertEqual(ReviewForm(invoice=row,actor=self.actor)['tax_rule'].value(),self.rule.pk)
        draft=self.draft(tax_rule=self.rule)
        self.assertEqual(SaleForm(instance=draft,actor=self.actor)['tax_rule'].value(),self.rule.pk)
