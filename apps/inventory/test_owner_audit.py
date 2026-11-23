from decimal import Decimal as D
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from .models import StockBalance, StockMovement, StockOperation
from .tests import StockFixtures, DAY


class OwnerAuditTests(StockFixtures, TestCase):
    def test_missing_zero_balance_is_not_silently_accepted(self):
        self.op('OPENING',quantity=D('0'),cost=D('7'))
        StockBalance.objects.filter(product=self.p,location=self.loc).delete()
        with self.assertRaisesMessage(CommandError,'sem saldo local correspondente'):
            call_command('check_inventory')

    def test_snapshot_with_valid_delta_but_wrong_start_is_detected(self):
        self.op()
        original=StockMovement.objects.get()
        # Insert a synthetic zero movement with internally consistent, false position.
        # Do not update protected ledger rows or disable PostgreSQL triggers.
        operation=StockOperation.objects.create(kind='REVALUE',actor=self.actor,date=DAY,reason='Teste',fingerprint='audit')
        fields={f.name:getattr(original,f.name) for f in original._meta.fields
            if f.name not in {'id','operation'}}
        fields.update(quantity=D('0'),value=D('0'),cost_variance=D('0'),
            owner_before_quantity=D('99'),owner_after_quantity=D('99'),
            owner_before_value=D('495'),owner_after_value=D('495'))
        StockMovement.objects.create(operation=operation,**fields)
        with self.assertRaisesMessage(CommandError,'histórico acumulado'):
            call_command('check_inventory')


from unittest.mock import patch
from django.db import connection
from django.test import TransactionTestCase
from .management.commands.check_inventory import Command


class OwnerAuditTransactionTests(TransactionTestCase):
    def test_cli_uses_read_only_repeatable_snapshot(self):
        observed = []
        def inspect(command):
            with connection.cursor() as cursor:
                cursor.execute('SHOW transaction_isolation')
                observed.append(cursor.fetchone()[0])
                cursor.execute('SHOW transaction_read_only')
                observed.append(cursor.fetchone()[0])
        with patch.object(Command, 'check_ledger', inspect):
            call_command('check_inventory')
        self.assertEqual(observed, ['repeatable read', 'on'])
        self.assertFalse(connection.in_atomic_block)
