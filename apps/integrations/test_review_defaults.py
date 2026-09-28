from decimal import Decimal as D
from uuid import uuid4
from django.test import TestCase
from django.urls import reverse
from apps.sales.tests import Fixture
from apps.sales.models import SalesChannel, Sale
from apps.inventory.models import StockLocation
from apps.finance.models import FinancialTitle, FinancialEntry
from .tests import payload, ISSUER
from .models import BlingConnection, ReviewDefaults
from .services import stage, save_review_defaults
from .forms import ReviewForm


class ReviewDefaultsTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.connection = BlingConnection.objects.create(pk=1, issuer=ISSUER)
        self.full_channel = SalesChannel.objects.create(name='Canal Full sintético')
        self.full_location = StockLocation.objects.create(name='Depósito Full sintético')
        self.config = dict(full_store='42', full_channel=self.full_channel, full_location=self.full_location,
                           default_channel=self.channel, default_location=self.location)
        save_review_defaults(actor=self.actor, data=self.config)

    def invoice(self, store='42', **changes):
        return stage(actor=self.actor, connection=self.connection,
                     payload=payload(loja={'id': store}, valorFrete='12.34', **changes))

    def values(self, row):
        values = {k: str(v.pk if hasattr(v, 'pk') else v) if v is not None else '' for k,v in self.data().items()}
        values.update(revision=row.revision, key=str(uuid4()), **{'extras-TOTAL_FORMS':'0', 'extras-INITIAL_FORMS':'0'})
        return values

    def test_routing_full_and_every_other_store_and_inactive(self):
        for store in ['42', '77', '']:
            row=self.invoice(store)
            form=ReviewForm(invoice=row, actor=self.actor)
            self.assertEqual(form.initial['channel'], self.full_channel.pk if store=='42' else self.channel.pk)
            self.assertEqual(form.initial['location'], self.full_location.pk if store=='42' else self.location.pk)
        self.full_channel.active=False;self.full_channel.save()
        form=ReviewForm(invoice=self.invoice(), actor=self.actor)
        self.assertIsNone(form.initial['channel'])

    def test_freight_defaults_both_fields_and_zero_money_display(self):
        form=ReviewForm(invoice=self.invoice(), actor=self.actor)
        for name in ['shipping_received', 'shipping_paid']:
            self.assertEqual(form.initial[name], D('12.34'))
            self.assertIn('value="12,34"', str(form[name]))
        for name in ['discount','fees','difal','commission','other_costs']:
            self.assertIn('value="0,00"', str(form[name]))
        self.assertNotIn('reviewed', form.fields)
        self.assertNotIn('tax_override', [f.name for f in form.optional_fields])

    def test_manual_overrides_survive_post_and_errors_without_receivable(self):
        row=self.invoice()
        values=self.values(row)
        values.update(discount='1,50', shipping_received='9,00', shipping_paid='20,00',
                      tax_override='0', tax_reason='Injected override')
        self.client.force_login(self.actor)
        url=reverse('bling_detail',args=[row.pk])
        broken=dict(values, fees='invalid')
        response=self.client.post(url,broken)
        self.assertEqual(response.status_code,200)
        self.assertContains(response, 'value="20,00"')
        self.assertEqual(str(response.context['form']['channel'].value()),str(self.channel.pk))
        response=self.client.post(url,values)
        self.assertEqual(response.status_code,302)
        sale=Sale.objects.get()
        self.assertEqual(sale.location,self.location)
        self.assertEqual(sale.channel,self.channel)
        self.assertEqual(sale.discount,D('1.50'))
        self.assertEqual(sale.shipping_received,9)
        self.assertEqual(sale.shipping_paid,20)
        self.assertIsNone(sale.tax_override)
        self.assertGreater(sale.tax_amount,0)
        self.assertFalse(FinancialTitle.objects.exists())
        self.assertFalse(FinancialEntry.objects.exists())

    def test_no_rule_is_not_silently_zero_tax(self):
        row=self.invoice()
        form=ReviewForm(dict(self.values(row),tax_rule=''),invoice=row,actor=self.actor)
        self.assertFalse(form.is_valid())
        self.assertIn('tax_rule',form.errors)

    def test_defaults_admin_only_and_report_link_respects_permission(self):
        self.client.force_login(self.operator)
        response=self.client.post(reverse('bling_connection'),{})
        self.assertEqual(response.status_code,403)
        self.client.force_login(self.actor)
        response=self.client.get(reverse('bling_queue'))
        self.assertContains(response,reverse('sales_sheet'))
        self.assertEqual(ReviewDefaults.objects.count(),1)

    def test_configuration_form_saves_without_affecting_sales(self):
        self.client.force_login(self.actor)
        data={k: v.pk if hasattr(v,'pk') else v for k,v in self.config.items()}
        response=self.client.post(reverse('bling_connection'),data)
        self.assertEqual(response.status_code,302)
        self.assertFalse(Sale.objects.exists())
