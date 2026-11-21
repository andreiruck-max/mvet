from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from apps.finance.models import FinancialTitle, FinancialOperation
from apps.inventory.models import StockMovement
from .tests import Fixture
from .services import confirm_and_receive


class ConfirmReceiveTests(Fixture, TestCase):
    def test_receipt_is_atomic_and_idempotent(self):
        p = self.draft()
        revision = p.revision
        for _ in range(2):
            confirm_and_receive(actor=self.admin, purchase_id=p.pk, date=self.date, revision=revision)
        p.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(p.status, 'RECEIVED')
        self.assertEqual(self.product.quantity, 10)
        self.assertEqual(self.product.value, 50)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(FinancialTitle.objects.filter(purchase_installment__purchase=p).count(), 1)
        self.assertFalse(FinancialOperation.objects.exists())

    def test_invalid_receipt_rolls_back_commitment(self):
        p = self.draft()
        with self.assertRaises(ValidationError):
            confirm_and_receive(actor=self.admin, purchase_id=p.pk, date=self.date-timedelta(days=1), revision=p.revision)
        p.refresh_from_db()
        self.assertEqual(p.status, 'DRAFT')
        self.assertFalse(FinancialTitle.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_permissions_and_stale_revision(self):
        p = self.draft()
        with self.assertRaises(PermissionDenied):
            confirm_and_receive(actor=self.seller, purchase_id=p.pk, date=self.date, revision=p.revision)
        with self.assertRaises(ValidationError):
            confirm_and_receive(actor=self.admin, purchase_id=p.pk, date=self.date, revision=p.revision-1)
        self.client.force_login(self.seller)
        url = reverse('purchase_confirm_receive', args=[p.pk])
        self.assertEqual(self.client.post(url, {'date':self.date, 'revision':p.revision}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertContains(self.client.get(reverse('purchase_detail', args=[p.pk])), 'Confirmar compra e recebimento')
        self.assertEqual(self.client.post(url, {'date':self.date, 'revision':p.revision}).status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.status, 'RECEIVED')
