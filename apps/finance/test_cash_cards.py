from datetime import timedelta
from decimal import Decimal as D

from django.test import TestCase
from django.urls import reverse

from apps.reporting.tests import ReportingFixture
from . import services


class CashCardTests(ReportingFixture, TestCase):
    def test_today_card_is_independent_of_filter_and_projection(self):
        self.client.force_login(self.actor)
        future = self.today + timedelta(days=10)
        self.pay(self.title())
        self.pay(self.title(amount=D('100'), due_date=future), date=future)
        self.title(amount=D('50'), due_date=future)
        other = services.save_account(actor=self.actor, data=dict(
            name='Outra conta', kind='BANK', opening_date=self.company.cutover_date,
            opening_balance=D('200')))
        inactive = services.save_account(actor=self.actor, data=dict(
            name='Inativa', kind='BANK', opening_date=self.company.cutover_date,
            opening_balance=D('9000')))
        inactive.active = False
        inactive.save()
        for start in (self.today, self.today + timedelta(days=1)):
            for mode in ('actual', 'projected'):
                for account, today_total, projected in (
                    ('', D('1190'), D('1040')),
                    (self.account.pk, D('990'), D('840')),
                    (other.pk, D('200'), D('200')),
                ):
                    with self.subTest(start=start, mode=mode, account=account):
                        response = self.client.get(reverse('finance'), dict(
                            period='', start=start.isoformat(), end=future.isoformat(),
                            mode=mode, account=account))
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.context['today_summary']['actual'], today_total)
                        self.assertEqual(response.context['today_summary']['end'], self.today)
                        self.assertEqual(response.context['summary']['projected'], projected)
                        self.assertEqual(response.context['summary']['end'], future)
                        self.assertContains(response, 'Saldo realizado das contas ativas hoje · ' + self.today.strftime('%d/%m/%Y'))
                        self.assertContains(response, 'Projeção das contas ativas até ' + future.strftime('%d/%m/%Y'))
