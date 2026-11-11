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

    def test_default_month_pending_partial_and_highlights_match_export(self):
        from apps.reporting.datasets import build
        from datetime import date
        from unittest.mock import patch
        # Fix a date away from month boundaries; all dates remain after the fixture cutoff.
        today = self.today.replace(day=15)
        from apps.core.models import Company
        Company.objects.filter(pk=1).update(cutover_date=today.replace(day=1))
        overdue = self.expense(description='Pendente vencida', document_date=today.replace(day=1),
            competence=today, due_date=today-timedelta(days=1))
        due_today = self.expense(description='Pendente hoje', document_date=today.replace(day=1),
            competence=today, due_date=today)
        partial = self.expense(description='Parcial', document_date=today.replace(day=1),
            competence=today, due_date=today+timedelta(days=2))
        paid = self.expense(description='Paga integral', document_date=today.replace(day=1),
            competence=today, due_date=today)
        for expense, amount in [(partial, D('40')), (paid, D('100'))]:
            finance.settle(actor=self.admin,key=uuid4(),title_id=expense.title_id,
                account_id=self.account.pk,date=max(today, self.today),principal=amount,
                interest=D('0'),discount=D('0'),actual=amount,revision=0)
        next_month = (today.replace(day=28)+timedelta(days=4)).replace(day=1)
        self.expense(description='Outro mês', document_date=today.replace(day=1), competence=next_month,
            due_date=next_month)
        self.client.force_login(self.admin)
        with patch('django.utils.timezone.localdate', return_value=today):
            response = self.client.get(reverse('expenses'))
            self.assertEqual(response.context['form'].cleaned_data['period'], 'month')
            self.assertEqual(response.context['form'].cleaned_data['status'], 'pending')
            self.assertEqual([e.pk for e in response.context['page']], [overdue.pk, due_today.pk, partial.pk])
            self.assertEqual(response.context['summary']['pending'], D('260'))
            self.assertContains(response, 'expense-row-overdue')
            self.assertContains(response, 'Vence hoje')
            self.assertContains(response, 'Pendente: R$ 60,00')
            self.assertNotContains(response, 'Paga integral')
            self.assertNotContains(response, 'Outro mês')
            dataset = build('expenses', self.admin, {})
            self.assertEqual([r[1] for r in dataset.rows], ['Pendente vencida', 'Pendente hoje', 'Parcial'])
            response = self.client.get(reverse('expenses'), {'status':'paid'})
            self.assertEqual([e.pk for e in response.context['page']], [paid.pk])
            response = self.client.get(reverse('expenses'), {'period':'', 'status':'active'})
            self.assertEqual(response.context['page'].paginator.count, 5)
            self.assertEqual(self.client.get(reverse('expenses')).context['page'].paginator.count, 3)

    def test_explicit_date_range_is_not_replaced_by_default_month(self):
        self.assertEqual(selectors.list_filters({'start':'2026-01-01','end':'2026-02-01'}),
            {'start':'2026-01-01','end':'2026-02-01','status':'pending'})
        self.assertEqual(selectors.list_filters({'period':'','status':'all'}), {'period':'','status':'all'})
