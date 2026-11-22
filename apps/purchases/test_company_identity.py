from django.db import IntegrityError, transaction
from django.test import TestCase
from apps.core.models import Company
from .tests import Fixture
from .models import Purchase


class PurchaseCompanyTests(Fixture, TestCase):
    def test_receipt_preserves_owner_and_amounts(self):
        purchase = self.received()
        self.assertEqual(purchase.company_id, 1)
        self.assertEqual(set(purchase.items.values_list('company_id', flat=True)), {1})
        self.assertEqual(set(purchase.installments.values_list('company_id', flat=True)), {1})
        self.assertEqual(purchase.total, 50)
        self.assertEqual(purchase.installments.get().financial_title.company_id, 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)

    def test_secondary_draft_is_rejected_by_database(self):
        Company.objects.get_or_create(pk=2, defaults={'active': False})
        purchase = self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Purchase.objects.filter(pk=purchase.pk).update(company_id=2)
        purchase.refresh_from_db()
        self.assertEqual(purchase.company_id, 1)
