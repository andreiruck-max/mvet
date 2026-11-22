from django.db import IntegrityError, transaction
from django.test import TestCase
from apps.core.models import Company
from .tests import Fixture
from .models import FinancialTitle, FinancialOperation, FinancialEntry


class LedgerCompanyTests(Fixture, TestCase):
    def test_settlement_keeps_owner_and_rejects_cross_company_title(self):
        Company.objects.get_or_create(pk=2, defaults={'active': False})
        title = self.title()
        self.settle(title)
        self.assertEqual(title.company_id, 1)
        self.assertEqual(set(FinancialOperation.objects.values_list('company_id', flat=True)), {1})
        self.assertEqual(set(FinancialEntry.objects.values_list('company_id', flat=True)), {1})
        with self.assertRaises(IntegrityError), transaction.atomic():
            FinancialTitle.objects.create(company_id=2, actor=self.admin, direction='PAY',
                description='Forbidden owner', date=self.today, due_date=self.today, amount=10)
