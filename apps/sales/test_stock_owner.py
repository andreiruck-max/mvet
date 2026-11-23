from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from apps.accounts.company_context import CompanyScope
from apps.inventory.models import StockOperation
from apps.inventory.services import validate_operation_owner
from .services import confirm, cancel
from .tests import Fixture


class SaleStockOwnerTests(Fixture, TestCase):
    def test_group_cannot_reconfirm_or_cancel_sale(self):
        sale=self.confirmed()
        before=StockOperation.objects.count()
        self.actor._mvet_company_scope=CompanyScope((1,),group=True)
        with self.assertRaises(PermissionDenied):
            confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)
        with self.assertRaises(PermissionDenied):
            cancel(actor=self.actor,sale_id=sale.pk,reason='Teste')
        sale.refresh_from_db()
        self.assertEqual(sale.status,'CONFIRMED')
        self.assertEqual(StockOperation.objects.count(),before)

    def test_source_ledger_requires_same_owner(self):
        sale=self.confirmed()
        self.assertEqual(sale.stock_operation.company_id,sale.company_id)
        self.assertEqual(set(sale.items.get().consumptions.values_list('company_id',flat=True)),{1})
        operation=sale.stock_operation
        operation.company_id=2  # In-memory mismatch: never disable PostgreSQL protections.
        with self.assertRaises(ValidationError):
            validate_operation_owner(operation,sale.company_id)
