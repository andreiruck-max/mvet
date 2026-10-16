from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
from django.test import TestCase
from django.urls import reverse
from apps.finance import services as finance
from .tests import Fixture
from . import selectors, services


class ExpenseSummaryTests(Fixture,TestCase):
    def test_partial_future_reversal_noncash_cancelled_and_filters(self):
        overdue=self.expense(document_date=self.cutoff,due_date=self.today-timedelta(days=1),category=self.category)
        op=finance.settle(actor=self.admin,key=uuid4(),title_id=overdue.title_id,account_id=self.account.pk,date=self.today,principal=D('40'),interest=D('3'),discount=D('2'),actual=D('41'),revision=0,notes='Encargos de teste')
        future=self.expense(amount=D('200'),category=self.other)
        finance.settle(actor=self.admin,key=uuid4(),title_id=future.title_id,account_id=self.account.pk,date=self.today+timedelta(days=1),principal=D('200'),interest=D('0'),discount=D('0'),actual=D('200'),revision=0)
        depreciation=services.save_category(actor=self.admin,data=dict(code='08',name='Depreciação',nature='DEPRECIATION'))
        self.expense(amount=D('30'),category=depreciation)
        cancelled=self.expense(amount=D('70'))
        services.cancel_expense(actor=self.admin,pk=cancelled.pk,reason='Teste de cancelamento')
        summary=selectors.expense_summary(selectors.expenses({'status':'all'}))
        self.assertEqual(summary,dict(total=D('330'),settled=D('240'),pending=D('60'),overdue=D('60'),noncash=D('30'),cancelled=D('70')))
        self.assertEqual(selectors.expense_summary(selectors.expenses({'category':self.other}))['total'],D('200'))
        finance.reverse(actor=self.admin,pk=op.pk,date=self.today,reason='Teste de estorno')
        self.assertEqual(selectors.expense_summary(selectors.expenses({}))['pending'],D('100'))

    def test_totals_all_pages_empty_invalid_and_permissions(self):
        for i in range(31):self.expense(amount=D('1.01'))
        self.client.force_login(self.admin)
        response=self.client.get(reverse('expenses'),{'page':2})
        self.assertEqual(response.context['summary']['total'],D('31.31'))
        self.assertEqual(len(response.context['page']),1)
        self.assertContains(response,'data-auto-filter')
        self.assertEqual(self.client.get(reverse('expenses'),{'q':'absent'}).context['summary']['total'],0)
        self.assertEqual(self.client.get(reverse('expenses'),{'start':'invalid'}).context['summary']['total'],0)
        self.client.force_login(self.operator)
        self.assertNotContains(self.client.get(reverse('expenses')),'Resumo das despesas')
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(reverse('expenses')).status_code,403)
