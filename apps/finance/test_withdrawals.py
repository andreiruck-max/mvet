from decimal import Decimal as D
from django.test import TestCase
from django.urls import reverse
from apps.reporting.tests import ReportingFixture
from . import selectors, services

class WithdrawalTests(ReportingFixture,TestCase):
    def test_withdrawals_partial_payments_and_reversal(self):
        from uuid import uuid4
        title=self.title(amount=D('100'),category='WITHDRAWAL',counterparty='Sócio teste')
        op=services.settle(actor=self.actor,key=uuid4(),title_id=title.pk,account_id=self.account.pk,date=self.today,principal=D('40'),interest=D('0'),discount=D('0'),actual=D('40'),notes='',revision=title.revision)
        result=selectors.withdrawals(self.today,self.today)
        self.assertEqual(result['net'],D('40'))
        self.assertEqual(result['people'],[('Sócio teste',D('40'))])
        self.client.force_login(self.actor)
        self.assertContains(self.client.get(reverse('financial_withdrawals')),'40,00')
        from apps.reporting.selectors import financial_result
        self.assertEqual(financial_result(self.period)['expense'],D('0'))
        services.reverse(actor=self.actor,pk=op.pk,date=self.today,reason='Teste de estorno')
        result=selectors.withdrawals(self.today,self.today)
        self.assertEqual(result['outgoing'],D('40'))
        self.assertEqual(result['incoming'],D('40'))
        self.assertEqual(result['net'],D('0'))
