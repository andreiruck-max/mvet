from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from .tests import Fixture
from . import services, selectors
from .models import FinancialEntry, FinancialTitle


class AccountFlowTests(Fixture, TestCase):
    def test_credit_and_debit_shortcuts_preselect_direction(self):
        self.client.force_login(self.admin)
        page=self.client.get(reverse('financial_account',args=[self.a.pk]))
        self.assertContains(page,'Novo crédito');self.assertContains(page,'Novo débito')
        for direction in ('RECEIVE','PAY'):
            form=self.client.get(reverse('financial_account_entry',args=[self.a.pk]),{'direction':direction}).context['form']
            self.assertEqual(form['direction'].value(),direction)

    def entry(self, **changes):
        data=dict(actor=self.admin,account_id=self.a.pk,key=uuid4(),direction='PAY',date=self.today,
                  description='Teste de caixa',amount=D('25'),category='PRINCIPAL',notes='')
        data.update(changes)
        return services.account_entry(**data)

    def test_default_fifteen_days_and_whole_custom_period(self):
        self.client.force_login(self.admin)
        response=self.client.get(reverse('finance'))
        days=response.context['days']
        self.assertEqual(len(days),16)
        self.assertEqual(days[0]['date'],self.today)
        self.assertEqual(days[-1]['date'],self.today+timedelta(days=15))
        self.assertFalse(response.context['page'].has_other_pages())
        response=self.client.get(reverse('finance'),{'start':self.today,'end':self.today+timedelta(days=60),'page':2})
        self.assertEqual(len(response.context['days']),61)

    def test_inactive_removed_from_flow_not_history_or_company_reporting(self):
        self.entry()
        services.save_account(actor=self.admin,pk=self.a.pk,data={'active':False,'name':'Banco arquivado'})
        self.client.force_login(self.admin)
        response=self.client.get(reverse('finance'))
        self.assertEqual([row['account'].pk for row in response.context['matrix']],[self.b.pk])
        self.assertEqual(response.context['summary']['actual'],0)
        self.assertEqual(selectors.cash_summary(self.today,self.today)['actual'],975)
        self.assertContains(self.client.get(reverse('financial_account',args=[self.a.pk])),'Teste de caixa')
        with self.assertRaises(ValidationError):self.entry()
        self.assertEqual(FinancialEntry.objects.count(),1)
        services.save_account(actor=self.admin,pk=self.a.pk,data={'active':True})
        self.assertEqual(self.client.get(reverse('finance')).context['summary']['actual'],975)

    def test_entry_atomic_idempotent_permissions_and_future(self):
        key=uuid4();first=self.entry(key=key)
        self.assertEqual(self.entry(key=key).pk,first.pk)
        self.assertEqual(FinancialEntry.objects.count(),1)
        self.assertEqual(FinancialTitle.objects.get().remaining,0)
        with self.assertRaises(ValidationError):self.entry(key=key,amount=D(30))
        with self.assertRaises(PermissionDenied):self.entry(actor=self.seller)
        self.assertEqual(FinancialTitle.objects.count(),1)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(reverse('financial_account',args=[self.a.pk])).status_code,403)
        self.assertEqual(self.client.post(reverse('financial_account_entry',args=[self.a.pk]),{}).status_code,403)

    def test_statement_running_balance_order_backdate_and_reversal(self):
        debit=self.entry()
        self.entry(date=self.today-timedelta(days=1),direction='RECEIVE',amount=D(10))
        services.reverse(actor=self.admin,pk=debit.pk,date=self.today,reason='Teste de estorno')
        rows,initial=selectors.account_statement(self.a,self.today-timedelta(days=1),self.today)
        self.assertEqual(initial,1000)
        self.assertEqual([r.running_balance for r in rows],[D(1010),D(985),D(1010)])
        self.assertEqual(list(rows[1:2])[0].running_balance,985)

    def test_account_creation_joins_flow_and_edit_redirects_to_statement(self):
        self.client.force_login(self.admin)
        response=self.client.post(reverse('financial_account_new'),{'name':'Banco novo','kind':'BANK','opening_date':self.today,'opening_balance':'123.45','active':'on','institution':''})
        self.assertEqual(response.status_code,302)
        self.assertContains(self.client.get(response.url),'Banco novo')
        self.assertContains(self.client.get(reverse('finance')),'Banco novo')

    def test_future_manual_entries_project_once_and_reverse_before_date(self):
        day=self.today+timedelta(days=4)
        debit=self.entry(date=day)
        self.entry(date=day,direction='RECEIVE',amount=D(10))
        summary=selectors.cash_summary(self.today,day)
        self.assertEqual(summary['actual'],1000)
        self.assertEqual(summary['projected'],985)
        self.assertEqual(FinancialTitle.objects.filter(settled=0).count(),0)
        services.reverse(actor=self.admin,pk=debit.pk,date=self.today,reason='Cancelar débito futuro')
        summary=selectors.cash_summary(self.today,day)
        self.assertEqual(summary['actual'],1000)
        # Direct entries have no independent obligation after reversal.
        self.assertEqual(summary['projected'],1010)

    def test_bank_month_default_with_return_url_and_descending_balances(self):
        from calendar import monthrange
        self.entry(direction='RECEIVE',amount=D('10'),description='Primeiro crédito')
        self.entry(amount=D('25'),description='Último débito')
        self.client.force_login(self.admin)
        response=self.client.get(reverse('financial_account',args=[self.a.pk]),{'next':'/financeiro/'})
        self.assertEqual(response.status_code,200)
        form=response.context['form']
        self.assertEqual(form.cleaned_data['start'],self.today.replace(day=1))
        self.assertEqual(form.cleaned_data['end'],self.today.replace(day=monthrange(self.today.year,self.today.month)[1]))
        rows=list(response.context['page'])
        self.assertEqual([r.operation.description for r in rows],['Último débito','Primeiro crédito'])
        self.assertEqual([r.running_balance for r in rows],[D('985'),D('1010')])
        self.assertEqual(response.context['today_summary']['actual'],985)
        self.assertNotContains(response,'Selecione um período ou informe as duas datas.')

    def test_bank_closing_forecast_does_not_change_today_balance(self):
        end=self.today+timedelta(days=5)
        self.title(due_date=end,amount=D('100'))
        self.client.force_login(self.admin)
        response=self.client.get(reverse('financial_account',args=[self.a.pk]),{'start':self.today,'end':end})
        self.assertEqual(response.context['today_summary']['actual'],1000)
        self.assertEqual(response.context['summary']['closing'],900)
        self.assertContains(response,'Saldo previsto no último dia')
        response=self.client.get(reverse('financial_account',args=[self.a.pk]),{'start':self.today,'end':self.today})
        self.assertEqual(response.context['summary']['closing'],1000)
        self.assertContains(response,'Saldo realizado no último dia')
