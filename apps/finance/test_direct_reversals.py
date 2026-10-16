from datetime import timedelta
from decimal import Decimal as D
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from django.apps import apps
from django.db import connection
from django.test import TestCase
from apps.core.models import AuditLog
from .tests import Fixture
from . import services as s, selectors
from .models import FinancialTitle as Title, FinancialEntry as Entry


class DirectReversalTests(Fixture, TestCase):
    def direct(self, account, direction='RECEIVE', date=None):
        return s.account_entry(actor=self.admin, account_id=account.pk, key=uuid4(), direction=direction,
            date=date or self.today, description='Lançamento sintético', amount=D('75'), category='PRINCIPAL')

    def test_reversed_credit_and_debit_leave_no_forecast_in_any_account(self):
        for account in [self.a, self.b]:
            for direction in ['RECEIVE', 'PAY']:
                op = self.direct(account, direction)
                reverse = s.reverse(actor=self.admin, pk=op.pk, date=self.today, reason='Conta incorreta')
                self.assertEqual(s.reverse(actor=self.admin, pk=op.pk, date=self.today, reason='Reenvio').pk, reverse.pk)
                title = Title.objects.get(pk=op.title_id)
                self.assertEqual(title.status, 'CANCELLED')
                self.assertEqual(title.settled, 0)
                for end in [self.today, self.today + timedelta(days=20)]:
                    result = selectors.cash_summary(self.today, end, account.pk)
                    self.assertEqual(result['actual'], account.opening_balance)
                    self.assertEqual(result['projected'], account.opening_balance)
                rows, initial = selectors.account_statement(account, self.today, self.today)
                self.assertEqual(list(rows)[-1].running_balance, account.opening_balance)
        self.assertEqual(Entry.objects.count(), 8)
        self.assertEqual(selectors.cash_summary(self.today,self.today)['projected'], D('1000'))

    def test_future_direct_reversal_does_not_reopen_obligation(self):
        date = self.today + timedelta(days=5)
        op = self.direct(self.a, date=date)
        s.reverse(actor=self.admin, pk=op.pk, date=self.today, reason='Não ocorrerá')
        self.assertEqual(selectors.cash_summary(self.today,date,self.a.pk)['projected'], D('1000'))
        self.assertEqual(selectors.cash_summary(self.today,self.today,self.a.pk)['actual'], D('1000'))

    def test_real_obligation_still_reopens(self):
        title = s.create_title(actor=self.admin, key=uuid4(), data=dict(direction='PAY',description='Obrigação real',
            date=self.today,due_date=self.today,amount=D('75'),account=self.a))
        op = s.settle(actor=self.admin,key=uuid4(),title_id=title.pk,account_id=self.a.pk,date=self.today,
            principal=D('75'),interest=D(0),discount=D(0),actual=D('75'),revision=0)
        s.reverse(actor=self.admin,pk=op.pk,date=self.today,reason='Refazer pagamento')
        title.refresh_from_db(); self.assertEqual(title.status,'OPEN')
        self.assertEqual(selectors.cash_summary(self.today,self.today,self.a.pk)['projected'], D('925'))

    def test_repair_legacy_reversals_preserves_ledger_and_edited_obligations(self):
        originals = [self.direct(self.a), self.direct(self.b)]
        # Simulate pre-fix behavior, which reopened each direct-entry title.
        with patch('apps.finance.services._cancel_titles'):
            for op in originals:
                s.reverse(actor=self.admin,pk=op.pk,date=self.today,reason='Erro antigo')
        edited = Title.objects.get(pk=originals[1].title_id)
        s.schedule_title(actor=self.admin,pk=edited.pk,due_date=self.today+timedelta(days=2),
            account=self.b,notes='Compromisso revisado',revision=edited.revision)
        before = list(Entry.objects.values())
        repair = import_module('apps.finance.migrations.0004_cancel_reversed_direct_entries').repair
        repair(apps,SimpleNamespace(connection=connection))
        repair(apps,SimpleNamespace(connection=connection))
        self.assertEqual(Title.objects.get(pk=originals[0].title_id).status,'CANCELLED')
        edited.refresh_from_db(); self.assertEqual(edited.status,'OPEN')
        self.assertEqual(list(Entry.objects.values()),before)
        self.assertEqual(AuditLog.objects.filter(operation='repair_reversed_account_entry').count(),1)
        self.assertEqual(selectors.cash_summary(self.today,self.today,self.a.pk)['projected'],D('1000'))
