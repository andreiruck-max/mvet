from decimal import Decimal as D
from uuid import uuid4
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from apps.accounts.company_context import CompanyScope
from .models import StockOperation, StockMovement, StockBalance
from .services import _apply, _value_out, reverse, transfer_batch
from .tests import StockFixtures, DAY


class StockCompanyServiceTests(StockFixtures, TestCase):
    def test_secondary_owner_never_falls_back_to_primary_stock(self):
        self.op()
        before = list(StockBalance.objects.values())
        count = StockOperation.objects.count()
        with self.assertRaises(PermissionDenied):
            self.op(company_id=2)
        with self.assertRaises(PermissionDenied):
            _value_out(self.p,D('1'),self.loc,company_id=2)
        operation = StockOperation(company_id=2,actor=self.actor,kind='RECEIPT',date=DAY)
        with self.assertRaises(PermissionDenied):
            _apply(operation,self.fresh(),self.loc,D('1'),D('5'))
        self.assertEqual(list(StockBalance.objects.values()),before)
        self.assertEqual(StockOperation.objects.count(),count)

    def test_group_cannot_write_or_replay_existing_operation(self):
        key = uuid4()
        original = self.op(key=key)
        self.actor._mvet_company_scope = CompanyScope((1,),group=True)
        with self.assertRaises(PermissionDenied):
            self.op(key=key)
        with self.assertRaises(PermissionDenied):
            reverse(actor=self.actor,operation_id=original.pk,key=uuid4(),date=DAY,reason='Estorno')
        with self.assertRaises(PermissionDenied):
            transfer_batch(actor=self.actor,key=uuid4(),date=DAY,reason='Transferir',
                location_id=self.loc.pk,target_location_id=self.full.pk,items=[(self.p.pk,D('1'))])
        self.assertEqual(StockOperation.objects.count(),1)
        self.assertEqual(StockMovement.objects.count(),1)

    def test_primary_owner_transfer_and_replay_preserved(self):
        self.actor._mvet_company_scope = CompanyScope((1,))
        self.op()
        key = uuid4()
        args=dict(actor=self.actor,key=key,date=DAY,reason='Transferir',company_id=1,
            location_id=self.loc.pk,target_location_id=self.full.pk,items=[(self.p.pk,D('2'))])
        op=transfer_batch(**args)
        self.assertEqual(transfer_batch(**args).pk,op.pk)
        self.assertEqual(op.company_id,1)
        self.assertEqual(set(op.movements.values_list('company_id',flat=True)),{1})
        self.assertEqual(self.fresh().quantity,D('10'))
        self.assertEqual(self.p.value,D('50'))
