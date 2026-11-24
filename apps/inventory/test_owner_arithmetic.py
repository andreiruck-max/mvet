"""Internal ledger arithmetic; not authorization of secondary public operations."""
from decimal import Decimal as D
from uuid import uuid4
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from apps.core.models import Company
from apps.products.models import Product
from .models import StockBalance, StockMovement, StockOperation
from .services import _apply, _value_out, domain_lock
from .tests import StockFixtures, DAY


class OwnerArithmeticTests(StockFixtures, TestCase):
    def setUp(self):
        super().setUp()
        Company.objects.get_or_create(pk=2, defaults={'name':'Agro sintética', 'active':False})

    def leg(self, owner, quantity, value, kind='RECEIPT', reference=None):
        with transaction.atomic():
            domain_lock()
            product = Product.objects.select_for_update().get(pk=self.p.pk)
            operation = StockOperation.objects.create(company_id=owner, actor=self.actor,
                date=DAY, kind=kind, reason='Fixture interna de propriedade',
                key=uuid4(), fingerprint='synthetic-owner-test')
            return _apply(operation, product, self.loc, D(quantity), D(value),
                unit_cost=D(reference) if reference is not None else None)

    def position(self, owner):
        b=StockBalance.objects.get(company_id=owner, product=self.p, location=self.loc)
        return b.quantity, b.value, b.average_cost

    def assert_physical(self, first, second, physical):
        self.assertEqual(self.position(1)[0], D(first))
        self.assertEqual(self.position(2)[0], D(second))
        self.assertEqual(self.fresh().quantity, D(physical))
        call_command('check_inventory')

    def test_primary_supplies_secondary_without_second_physical_issue(self):
        self.leg(1, '10', '50')
        # Explicit provisional reference, not inherited silently from another CNPJ.
        self.leg(2, '0', '0', 'REVALUE', reference='5')
        sale=self.leg(2, '-2', '-10', 'SALE_OUT')
        self.assert_physical('10', '-2', '8')
        with transaction.atomic():
            self.leg(1, '-2', '-10', 'TRANSFER')
            self.leg(2, '2', '10', 'TRANSFER')
        self.assert_physical('8', '0', '8')
        sale.refresh_from_db()
        self.assertEqual((sale.value,sale.cost_variance), (D('-10'),D('0')))
        self.assertEqual(self.fresh().value, D('40'))

    def test_secondary_supplies_primary_without_second_physical_issue(self):
        self.leg(2, '5', '35')
        self.leg(1, '0', '0', 'REVALUE', reference='7')
        self.leg(1, '-3', '-21', 'SALE_OUT')
        self.assert_physical('-3', '5', '2')
        with transaction.atomic():
            self.leg(2, '-3', '-21', 'TRANSFER')
            self.leg(1, '3', '21', 'TRANSFER')
        self.assert_physical('0', '2', '2')
        self.assertEqual(self.fresh().value, D('14'))

    def test_external_receipt_changes_only_its_owner_cost(self):
        self.leg(1, '2', '10')
        self.leg(2, '5', '35')
        self.assert_physical('2', '5', '7')
        self.assertEqual(_value_out(self.p,D('1'),self.loc,company_id=1),D('5'))
        self.assertEqual(_value_out(self.p,D('1'),self.loc,company_id=2),D('7'))
        self.leg(2, '5', '65')
        self.assertEqual(self.position(1), (D('2'),D('10'),D('5')))
        self.assertEqual(self.position(2), (D('10'),D('100'),D('10')))
        self.assertEqual(Product.objects.filter(sku=self.p.sku).count(),1)
        self.assertEqual(StockBalance.objects.filter(product=self.p,location=self.loc).count(),2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockBalance.objects.create(company_id=2,product=self.p,location=self.loc)
        with self.assertRaises(PermissionDenied):
            self.op(company_id=2)
        call_command('check_inventory')

    def test_negative_sale_cannot_borrow_other_owner_reference(self):
        self.leg(1, '10', '50')
        with self.assertRaises(ValidationError):
            self.leg(2, '-1', '-5', 'SALE_OUT')
        self.assertFalse(StockBalance.objects.filter(company_id=2).exists())
        self.assertFalse(StockOperation.objects.filter(company_id=2).exists())
        self.assertEqual(self.fresh().quantity,D('10'))

    def test_failed_second_leg_rolls_back_both_owners(self):
        self.leg(1, '10', '50')
        before=list(StockBalance.objects.values())
        count=StockMovement.objects.count()
        with self.assertRaises(ValidationError), transaction.atomic():
            self.leg(1, '-2', '-10', 'TRANSFER')
            self.leg(2, '2', '-10', 'TRANSFER')
        self.assertEqual(list(StockBalance.objects.values()),before)
        self.assertEqual(StockMovement.objects.count(),count)
        self.assertEqual(self.fresh().quantity,D('10'))
