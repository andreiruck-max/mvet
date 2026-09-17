from datetime import timedelta, date
from decimal import Decimal as D
from uuid import uuid4
from django.contrib.auth.models import User, Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture as SalesFixture
from apps.sales import services as sales
from apps.sales.models import SalesChannel
from apps.expenses import services as expenses
from apps.finance import services as finance
from apps.finance.models import FinancialTitle as Title
from apps.purchases.models import Supplier
from apps.purchases import services as purchases
from . import selectors as s
from .forms import PeriodForm

class ReportingFixture(SalesFixture):
    def setUp(self):
        super().setUp();self.today=timezone.localdate()
        self.company.cutover_date=self.today-timedelta(days=60);self.company.save()
        self.rule.starts_on=self.company.cutover_date;self.rule.save()
        self.category=expenses.save_category(actor=self.actor,data=dict(code='04',name='Operacionais',nature='OPERATING'))
        self.fin_category=expenses.save_category(actor=self.actor,data=dict(code='05',name='Financeiras',nature='FINANCIAL'))
        self.account=finance.save_account(actor=self.actor,data=dict(name='Banco teste',kind='BANK',opening_date=self.company.cutover_date,opening_balance=D('1000')))
        self.period=dict(start=self.today,end=self.today)
    def expense(self,**changes):
        data=dict(document_date=self.today,competence=self.today,description='Serviço mensal',supplier=None,counterparty='Fornecedor',amount=D('10'),category=self.category,cost_center='',notes='',due_date=self.today,account=self.account,recurrence_enabled=False)
        data.update(changes);return expenses.create_expense(actor=self.actor,key=uuid4(),data=data)
    def title(self,**changes):
        data=dict(description='Título sintético',direction='PAY',counterparty='',date=self.today,due_date=self.today,amount=D('10'),category='PRINCIPAL',account=self.account,opening=False,notes='')
        data.update(changes);return finance.create_title(actor=self.actor,key=uuid4(),data=data)
    def pay(self,title,interest='0',discount='0',date=None):
        return finance.settle(actor=self.actor,key=uuid4(),title_id=title.pk,account_id=self.account.pk,date=date or self.today,principal=title.remaining,interest=D(interest),discount=D(discount),actual=title.remaining+D(interest)-D(discount),notes='Diferença explícita',revision=title.revision)
    def purchase(self):
        supplier=Supplier.objects.create(legal_name='Fornecedor de teste')
        p=purchases.save_draft(actor=self.actor,key=uuid4(),data=dict(supplier=supplier,document='C-1',series='',date=self.today,location=self.location,discount=D('0'),freight=D('0'),other_costs=D('0'),notes=''),items=[(self.product.pk,D('10'),D('5'))],installments=[(self.today,D('25'),''),(self.today+timedelta(days=30),D('25'),'')])
        return purchases.confirm(actor=self.actor,purchase_id=p.pk,revision=p.revision)

class ReportingTests(ReportingFixture,TestCase):
    def test_sales_totals_match_historical_formulas_and_weighted_margin(self):
        first=self.confirmed();second=self.confirmed(invoice_number='101',products_amount=D('200'))
        self.receive(self.product,D('20'),D('90'))
        r=s.sales_summary(s.sale_rows(self.period))
        self.assertEqual(r['revenue'],first.revenue+second.revenue)
        self.assertEqual(r['cmv'],D('20'));self.assertEqual(r['contribution'],first.contribution+second.contribution)
        self.assertEqual(r['margin'],r['contribution']/r['revenue']*100)
    def test_drafts_cancelled_and_other_periods_not_in_result(self):
        self.draft();sale=self.confirmed(invoice_number='2');sales.cancel(actor=self.actor,sale_id=sale.pk,reason='Cancelada')
        self.confirmed(invoice_number='3',date=self.today-timedelta(days=1))
        self.assertEqual(s.sales_summary(s.sale_rows({**self.period,'status':'all'}))['count'],0)
    def test_extra_fees_and_retroactive_tax_are_in_report(self):
        sale=sales.save_draft(actor=self.actor,key=uuid4(),data=self.data(),items=[(self.product.pk,D('1'))],extra_costs=[('MDR',D('3.50'))])
        sale=sales.confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)
        r=s.sales_summary(s.sale_rows(self.period));self.assertEqual(r['extra_costs_total'],D('3.50'));self.assertEqual(r['contribution'],sale.contribution)
        from apps.sales.taxes import change_rate
        change_rate(actor=self.actor,rule_id=self.rule.pk,rate=D('10'),effective_from=self.today-timedelta(days=1),base='REVENUE',reason='Correção retroativa',revision=0)
        changed=s.sales_summary(s.sale_rows(self.period))
        self.assertEqual(changed['cmv'],r['cmv']);self.assertEqual(changed['tax_amount'],D('9.50'))
        self.assertEqual(changed['contribution'],r['contribution']-D('4.75'))
    def test_expense_and_future_competence_not_cash(self):
        self.confirmed();e=self.expense();self.pay(e.title)
        self.expense(competence=self.today+timedelta(days=30))
        r=s.dre(self.period);self.assertEqual(r['expenses']['OPERATING'],10);self.assertEqual(r['ebitda'],D('53.25'))
    def test_financial_expense_not_ebitda_or_duplicate_payment(self):
        self.confirmed();e=self.expense(category=self.fin_category);self.pay(e.title)
        r=s.dre(self.period);self.assertEqual(r['ebitda'],D('63.25'));self.assertEqual(r['result'],D('53.25'))
    def test_manual_financial_title_uses_origin_not_payment(self):
        t=self.title(category='FINANCIAL');self.pay(t)
        self.title(direction='RECEIVE',category='FINANCIAL',amount=D('4'))
        r=s.dre(self.period);self.assertEqual(r['financial']['expense'],10);self.assertEqual(r['financial']['income'],4)
        self.assertEqual(r['result'],D('-6'))
    def test_purchase_principal_transfer_and_opening_are_excluded(self):
        p=self.purchase();self.pay(p.installments.first().financial_title)
        self.pay(self.title())
        self.title(category='FINANCIAL',opening=True,date=self.company.cutover_date-timedelta(days=1))
        account=finance.save_account(actor=self.actor,data=dict(name='Destino',kind='BANK',opening_date=self.today,opening_balance=D('0')))
        finance.transfer(actor=self.actor,key=uuid4(),source_id=self.account.pk,destination_id=account.pk,date=self.today,amount=D('25'),notes='',planned=False)
        self.assertEqual(s.dre(self.period)['result'],0)
    def test_additional_interest_and_reversal_effective_date(self):
        t=self.title(date=self.today-timedelta(days=1));op=self.pay(t,interest='2',date=self.today-timedelta(days=1))
        self.assertEqual(s.financial_result(dict(start=op.date,end=op.date))['expense'],2)
        finance.reverse(actor=self.actor,pk=op.pk,date=self.today,reason='Estorno')
        self.assertEqual(s.financial_result(self.period)['expense'],-2)
        self.assertEqual(s.financial_result(dict(start=op.date,end=self.today))['expense'],0)
    def test_unclassified_titles_and_abatements_warn_not_silently_subtract(self):
        self.expense(category=None);self.title(category='OTHER');self.pay(self.title(),discount='1')
        r=s.dre(self.period);self.assertTrue(r['provisional']);self.assertEqual(r['expenses']['NONE'],10)
        self.assertEqual(r['financial']['unresolved'],10);self.assertEqual(r['financial']['discounts'],1)
    def test_channel_filter_does_not_allocate_corporate_expenses(self):
        self.confirmed();other=SalesChannel.objects.create(name='Segundo canal');self.confirmed(invoice_number='2',channel=other)
        self.expense();r=s.dre({**self.period,'channel':self.channel})
        self.assertEqual(r['sales']['count'],1);self.assertEqual(r['expenses']['OPERATING'],10)
        self.assertIsNone(r['ebitda']);self.assertIsNone(r['result'])
        self.assertEqual(len(s.channel_summary(self.period)),2)
    def test_zero_revenue_has_no_percentage(self):
        self.confirmed(products_amount=D('0'),discount=D('0'),shipping_received=D('0'))
        self.assertIsNone(s.sales_summary(s.sale_rows(self.period))['margin'])
    def test_paid_purchase_list_totals_do_not_repeat_purchase(self):
        p=self.purchase();self.pay(p.installments.first().financial_title)
        d=dict(start=self.today,end=self.today+timedelta(days=31),status='all')
        r=s.payable_totals(s.payables(d));self.assertEqual(r,dict(amount=D('50'),paid=D('25'),pending=D('25')))
        self.assertEqual(s.payables({**d,'status':'pending'}).count(),1)
        self.assertEqual(s.payables({**d,'purchase_start':self.today+timedelta(days=1)}).count(),0)
    def test_totals_cover_all_pages_and_filters_persist(self):
        self.receive(self.product,D('100'),D('5'))
        for i in range(31):self.confirmed(invoice_number=str(i))
        self.client.force_login(self.actor)
        response=self.client.get(reverse('sales_sheet'),{**self.period,'page':2,'q':''})
        self.assertEqual(response.status_code,200);self.assertEqual(len(response.context['page']),1)
        self.assertEqual(response.context['totals']['count'],31);self.assertContains(response,'start=')
    def test_periods_leap_year_and_invalid_dates(self):
        f=PeriodForm({'start':'2024-01-01','end':'2024-12-31'});self.assertTrue(f.is_valid())
        for data in [{'start':'2024-01-01','end':'2025-01-01'},{'start':'x','end':'2024-12-31'},{'start':'2024-01-02','end':'2024-01-01'}]:self.assertFalse(PeriodForm(data).is_valid())
        f=PeriodForm({'period':'last7'});self.assertTrue(f.is_valid());self.assertEqual((f.cleaned_data['end']-f.cleaned_data['start']).days,6)
    def test_cash_days_pagination_preserves_balances_and_empty_days(self):
        self.client.force_login(self.actor);d=dict(start=self.today,end=self.today+timedelta(days=30),page=2)
        r=self.client.get(reverse('finance'),d);self.assertEqual(r.status_code,200)
        self.assertEqual(len(r.context['days']),14);self.assertEqual(r.context['days'][0]['date'],self.today+timedelta(days=14))
        self.assertEqual(r.context['days'][0]['rows'][0]['final'],1000)
    def test_operator_denied_reports_and_post_not_accepted(self):
        self.client.force_login(self.operator)
        for name in ['dashboard','sales_sheet','dre','dre_api','dashboard_api','purchase_payables']:
            self.assertEqual(self.client.get(reverse(name)).status_code,403)
        self.client.force_login(self.actor)
        self.assertEqual(self.client.post(reverse('dre_api')).status_code,405)
    def test_dashboard_permission_does_not_leak_bank_stock_or_dre(self):
        user=User.objects.create_user('report-only');user.user_permissions.add(Permission.objects.get(codename='view_dashboard'))
        self.client.force_login(user);r=self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code,200);self.assertNotIn('cash_today',r.context);self.assertNotIn('stock',r.context);self.assertNotIn('dre',r.context)
        for name in ['dre_api','purchase_payables']:self.assertEqual(self.client.get(reverse(name)).status_code,403)
    def test_invalid_filters_return_error_not_unfiltered_totals(self):
        self.client.force_login(self.actor)
        for name in ['dashboard','sales_sheet','dre','dre_api','dashboard_api','purchase_payables']:
            self.assertEqual(self.client.get(reverse(name),{'start':'invalid'}).status_code,400)
    def test_report_api_decimal_strings_and_all_pages_render(self):
        self.confirmed();self.expense();self.purchase();self.client.force_login(self.actor)
        for name in ['dashboard','sales_sheet','dre','purchase_payables']:
            self.assertEqual(self.client.get(reverse(name)).status_code,200)
        data=self.client.get(reverse('dre_api'),self.period).json();self.assertIsInstance(data['ebitda'],str);self.assertEqual(D(data['ebitda']),D('53.25'))
