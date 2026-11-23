from django.core.exceptions import PermissionDenied
from django.test import TestCase
from apps.accounts.company_context import CompanyScope
from apps.inventory.models import StockOperation
from .services import confirm, receive, cancel
from .tests import Fixture


class PurchaseStockOwnerTests(Fixture, TestCase):
    def test_group_cannot_receive_or_replay_confirmation(self):
        purchase=self.ordered()
        self.buyer._mvet_company_scope=CompanyScope((1,),group=True)
        with self.assertRaises(PermissionDenied):
            confirm(actor=self.buyer,purchase_id=purchase.pk,revision=purchase.revision)
        with self.assertRaises(PermissionDenied):
            receive(actor=self.buyer,purchase_id=purchase.pk,revision=purchase.revision,date=self.date)
        with self.assertRaises(PermissionDenied):
            cancel(actor=self.buyer,purchase_id=purchase.pk,reason='Teste')
        purchase.refresh_from_db()
        self.assertEqual(purchase.status,'ORDERED')
        self.assertFalse(StockOperation.objects.exists())

    def test_receipt_and_return_keep_purchase_owner(self):
        purchase=self.received()
        self.assertEqual(purchase.receipt.company_id,purchase.company_id)
        purchase=cancel(actor=self.admin,purchase_id=purchase.pk,reason='Teste')
        self.assertEqual(purchase.reversal.company_id,purchase.company_id)
        self.assertEqual(set(purchase.reversal.movements.values_list('company_id',flat=True)),{1})
