from decimal import Decimal as D
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from apps.accounts.company_context import CompanyScope
from apps.core.models import Company
from apps.finance.models import FinancialAccount, FinancialEntry, FinancialTitle
from apps.finance.services import create_purchase_titles
from apps.inventory.models import StockOperation
from apps.inventory.services import _apply
from .models import Purchase, PurchaseItem, Supplier
from .services import save_draft, save_supplier
from .tests import Fixture


def other_receipt(fixture):
    Company.objects.get_or_create(pk=2, defaults={'active': False})
    return StockOperation.objects.create(company_id=2, actor=fixture.admin, date=fixture.date,
        kind='PUR_RECEIPT', reason='Recebimento sintético de outra empresa', fingerprint='other-owner')


class PurchaseOwnerLinkTests(Fixture, TestCase):
    def test_purchase_cannot_point_to_another_owners_receipt_or_return(self):
        operation = other_receipt(self)
        purchase = self.draft()
        for field, constraint in [('receipt_id', 'purchase_owner_receipt_fk'),
                                  ('reversal_id', 'purchase_owner_reversal_fk')]:
            with self.subTest(field=field):
                with self.assertRaises(IntegrityError) as error, transaction.atomic():
                    Purchase.objects.filter(pk=purchase.pk).update(**{field: operation.pk})
                self.assertEqual(error.exception.__cause__.diag.constraint_name, constraint)
        purchase.refresh_from_db()
        self.assertIsNone(purchase.receipt_id)
        self.assertIsNone(purchase.reversal_id)

    def test_same_sku_depot_quantity_and_price_do_not_make_a_foreign_receipt_valid(self):
        purchase = self.ordered()
        item = purchase.items.get()
        operation = other_receipt(self)
        movement = _apply(operation, self.product, self.location, item.quantity, item.allocated_total)
        with self.assertRaises(IntegrityError) as error, transaction.atomic():
            PurchaseItem.objects.filter(pk=item.pk).update(movement=movement)
        self.assertEqual(error.exception.__cause__.diag.constraint_name, 'purchase_owner_movement_fk')
        item.refresh_from_db()
        self.assertIsNone(item.movement_id)
        self.assertFalse(self.product.balances.filter(company_id=1).exists())

    def test_replay_edit_supplier_and_title_generation_require_an_individual_scope(self):
        args = dict(actor=self.admin,key=uuid4(),data=self.data(),items=[(self.product.pk,D('10'),D('5'))],
                    installments=[(self.date,D('50'),'')])
        purchase = save_draft(**args)
        for scope in (CompanyScope((1,),group=True), CompanyScope((2,))):
            self.admin._mvet_company_scope = scope
            for extra in ({}, {'key': uuid4()}, {'purchase_id': purchase.pk, 'revision': purchase.revision}):
                with self.subTest(scope=scope, extra=extra), self.assertRaises(PermissionDenied):
                    save_draft(**dict(args, **extra))
            with self.assertRaises(PermissionDenied):
                create_purchase_titles(purchase, self.admin)
            with self.assertRaises(PermissionDenied):
                save_supplier(actor=self.admin, data={'legal_name':'Fornecedor de outro contexto'})
        self.assertEqual(Supplier.objects.count(), 1)
        self.assertEqual(Purchase.objects.get().revision, 1)
        self.assertFalse(FinancialTitle.objects.exists())

    def test_owner_and_forecast_account_follow_each_installment_without_bank_debit(self):
        account = FinancialAccount.objects.create(name='Conta prevista',kind='BANK',opening_date=self.date)
        purchase = self.received(account=account,installments=[(self.date,D('20'),''),(self.date,D('30'),'')])
        titles = FinancialTitle.objects.filter(purchase_installment__purchase=purchase).order_by('purchase_installment__number')
        self.assertEqual(list(titles.values_list('company_id','account_id','amount')),
                         [(purchase.company_id,account.pk,D('20')), (purchase.company_id,account.pk,D('30'))])
        self.assertFalse(FinancialEntry.objects.exists())
        account.active=False;account.save(update_fields=['active'])
        with self.assertRaisesMessage(ValidationError, 'Conta prevista inativa'):
            self.draft(document='101',account=account)
        self.assertEqual(Purchase.objects.count(), 1)


class PurchaseOwnerHistoryTests(Fixture, TransactionTestCase):
    def test_inconsistent_historical_link_stops_migration_without_rewriting_history(self):
        operation = other_receipt(self)
        purchase = self.draft()
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            MigrationExecutor(connection).migrate([('purchases','0008_purchase_company_identity')])
            Purchase.objects.filter(pk=purchase.pk).update(receipt=operation)
            with self.assertRaises(IntegrityError) as error:
                MigrationExecutor(connection).migrate([('purchases','0009_purchase_owner_links')])
            self.assertEqual(error.exception.__cause__.diag.constraint_name, 'purchase_owner_receipt_fk')
            self.assertEqual(Purchase.objects.get(pk=purchase.pk).receipt_id, operation.pk)
        finally:
            Purchase.objects.filter(pk=purchase.pk).update(receipt=None)
            MigrationExecutor(connection).migrate(latest)
