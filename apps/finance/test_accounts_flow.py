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
    def entry(self, **changes):
        data=dict(actor=self.admin,account_id=self.a.pk,key=uuid4(),direction='PAY',date=self.today,
                  description='Teste de caixa',amount=D('25'),category='PRINCIPAL',notes='')
        data.update(changes)
        return services.account_entry(**data)

    def test_default_fifteen_days_and_whole_custom_period(self):
        self.client.force_login(self.admin)
        response=self.client.get(reverse('finance'))
        days=response.context['days']
        self.assertEqual(len(days),15)
        self.assertEqual(days[0]['date'],self.today-timedelta(days=1))
        self.assertEqual(days[-1]['date'],self.today+timedelta(days=13))
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
        with self.assertRaises(ValidationError):self.entry(date=self.today+timedelta(days=1))
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
