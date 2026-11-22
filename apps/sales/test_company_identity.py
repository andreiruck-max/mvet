from django.db import IntegrityError, transaction
from django.test import TestCase
from apps.core.models import Company
from .tests import Fixture
from .models import Sale


class SaleCompanyTests(Fixture, TestCase):
    def test_confirmation_preserves_cmv_tax_and_consumption_owner(self):
        sale = self.confirmed()
        self.assertEqual(sale.company_id, 1)
        item = sale.items.get()
        self.assertEqual(item.company_id, 1)
        self.assertEqual(item.consumptions.get().company_id, 1)
        self.assertEqual(sale.cmv, 10)
        self.assertEqual(str(sale.tax_amount), '4.75')
        self.receive(self.product, 10, 20)
        sale.refresh_from_db()
        self.assertEqual(sale.cmv, 10)

    def test_secondary_draft_is_rejected(self):
        Company.objects.get_or_create(pk=2, defaults={'active': False})
        sale = self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sale.objects.filter(pk=sale.pk).update(company_id=2)
