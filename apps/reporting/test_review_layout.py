from decimal import Decimal as D
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from .tests import ReportingFixture
from . import selectors,drilldown
from apps.sales.services import cancel


class ReviewLayoutTests(ReportingFixture,TestCase):
    def test_purchase_variance_and_reversed_interest_reconcile(self):
        from datetime import timedelta
        from uuid import uuid4
        from apps.purchases import services as purchases
        from apps.purchases.models import Supplier
        from apps.finance import services as finance
        from apps.sales.services import confirm
        supplier=Supplier.objects.create(legal_name='Fornecedor sintético')
        purchase=purchases.save_draft(actor=self.actor,key=uuid4(),data=dict(supplier=supplier,document='P-2',series='',date=self.today,location=self.location,discount=D(0),freight=D(0),other_costs=D(0),notes=''),items=[dict(product_id=None,name='Embalagens',quantity=D(1),unit_cost=D(20),moves_stock=False,category_id=self.category.pk)],installments=[(self.today,D(20),'')])
        purchases.confirm(actor=self.actor,purchase_id=purchase.pk,revision=purchase.revision)
        sale=self.draft(items=[(self.product.pk,D(12))])
        confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)
        self.receive(self.product,D(2),D(3))
        op=self.pay(self.title(date=self.today-timedelta(days=1)),interest='2',date=self.today-timedelta(days=1))
        finance.reverse(actor=self.actor,pk=op.pk,date=self.today,reason='Correção de teste')
        self.client.force_login(self.actor)
        response=self.client.get(reverse('dre'),self.period)
        self.assertEqual(response.context['report']['expenses']['OPERATING'],16)
        self.assertEqual(response.context['report']['financial']['expense'],-2)
        links=[(r['url'],r['value']) for r in response.context['lines'] if r['url']]
        links += [(g['url'],g['amount']) for g in response.context['report']['groups']]
        for url,total in links:
            detail=self.client.get(url)
            self.assertEqual(detail.status_code,200)
            self.assertEqual(detail.context['total'],total)

    def test_columns_detect_other_pages_and_values_align(self):
        for index in range(51):self.confirmed(invoice_number=str(index+100),difal=D(7) if index==0 else D(0),fees=D(0),commission=D(0),other_costs=D(0))
        self.client.force_login(self.actor)
        response=self.client.get(reverse('sales_sheet'),self.period)
        columns=response.context['columns'];keys=[c['key'] for c in columns]
        self.assertIn('difal',keys);self.assertNotIn('fees',keys);self.assertIn('tax_amount',keys)
        group=response.context['groups'][0]
        self.assertEqual(group['total_cells'][keys.index('difal')]['value'],7)
        for sale in group['rows']:
            self.assertEqual([c['key'] for c in sale.report_cells],keys)
        self.assertNotContains(response,'Composição');self.assertContains(response,'Produto teste')

    def test_negative_result_and_restricted_totals(self):
        self.confirmed(products_amount=D(1),discount=D(0),shipping_received=D(0))
        self.client.force_login(self.actor)
        response=self.client.get(reverse('sales_sheet'),self.period)
        self.assertContains(response,'result-negative')
        self.operator.user_permissions.add(Permission.objects.get(codename='view_sales_report'))
        self.client.force_login(self.operator)
        response=self.client.get(reverse('sales_sheet'),self.period)
        keys=[c['key'] for c in response.context['columns']]
        self.assertNotIn('cmv',keys);self.assertNotIn('contribution',keys)
        totals={c['key']:c['value'] for c in response.context['groups'][0]['total_cells']}
        self.assertIsNone(totals['tax_amount'])

    def test_every_dre_link_reconciles_and_master_gate_is_backend(self):
        self.confirmed();expense=self.expense();self.expense(category=self.fin_category,amount=D(3))
        title=self.title(category='FINANCIAL');self.pay(title,interest='2')
        self.client.force_login(self.actor)
        response=self.client.get(reverse('dre'),self.period)
        links=[(r['url'],r['value']) for r in response.context['lines'] if r['url']]
        links += [(g['url'],g['amount']) for g in response.context['report']['groups']]
        for url,total in links:
            detail=self.client.get(url)
            self.assertEqual(detail.status_code,200,url)
            self.assertEqual(detail.context['total'],total,url)
        target=response.context['report']['groups'][0]['url']
        self.operator.user_permissions.add(Permission.objects.get(codename='view_dre'))
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(target).status_code,403)
        self.assertNotContains(self.client.get(reverse('dre'),self.period),'/dre/lancamentos/')
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse('dre_sources'),{**self.period,'source':'invalid'}).status_code,404)
        self.assertEqual(self.client.post(target).status_code,405)

    def test_historical_category_keeps_separate_origins_and_extra_prefill(self):
        first=self.expense()
        self.category.name='Nome novo';self.category.save(update_fields=['name'])
        second=self.expense(amount=D(4))
        self.client.force_login(self.actor)
        response=self.client.get(reverse('dre'),self.period)
        groups=response.context['report']['groups'];self.assertEqual(len(groups),2)
        for group in groups:
            detail=self.client.get(group['url'])
            self.assertEqual(detail.context['total'],group['amount']);self.assertEqual(len(detail.context['page']),1)
            new=self.client.get(detail.context['new_expense'])
            self.assertEqual(new.context['form']['category'].value(),self.category.pk)

    def test_cancelled_sale_excluded_from_dre_sources_and_channel_preserved(self):
        sale=self.confirmed();cancel(actor=self.actor,sale_id=sale.pk,reason='Teste')
        data=dict(self.period,channel=self.channel)
        url=drilldown.url({'kind':'sale','field':'fees','label':'Taxas'},data)
        self.client.force_login(self.actor);response=self.client.get(url)
        self.assertEqual(response.context['total'],0)
        self.assertIn('channel='+str(self.channel.pk),response.context['back'])
