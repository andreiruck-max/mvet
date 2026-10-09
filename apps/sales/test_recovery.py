from decimal import Decimal as D
from uuid import uuid4
from unittest import skipUnless
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, transaction, DatabaseError
from django.test import TestCase
from django.urls import reverse
from apps.finance.models import FinancialTitle
from apps.inventory.models import StockMovement
from apps.reporting.selectors import sales_summary
from .models import Sale, SaleRecovery
from .services import confirm, cancel
from .recovery import recover_sale
from .tests import Fixture


class RecoveryTests(Fixture,TestCase):
    def cancelled(self):
        sale=self.draft(fees=D('41.62'))
        sale=confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)
        return cancel(actor=self.actor,sale_id=sale.pk,reason='Taxa errada')

    def recover(self,sale,**overrides):
        values=dict(actor=self.actor,sale_id=sale.pk,revision=sale.revision,key=uuid4(),fees=D('20.81'),reason='Correção de taxa e cancelamento por engano')
        values.update(overrides)
        return recover_sale(**values)

    def test_recovery_keeps_snapshots_updates_results_and_can_be_cancelled_again(self):
        sale=self.cancelled();old_cmv=sale.cmv;old_tax=sale.tax_snapshot;old_date=sale.date
        original=sale.stock_operation_id;returned=sale.return_operation_id;revision=sale.revision;key=uuid4()
        self.assertEqual(sales_summary(Sale.objects.all())['count'],0)
        count=StockMovement.objects.count()
        sale=self.recover(sale,key=key)
        self.assertEqual(sale.status,'CONFIRMED');self.assertEqual(sale.fees,D('20.81'))
        self.assertEqual((sale.cmv,sale.tax_snapshot,sale.date),(old_cmv,old_tax,old_date))
        self.assertEqual(sale.stock_operation.reversal_of_id,returned)
        self.assertEqual(sale.items.get().consumptions.get().movement.operation_id,original)
        self.assertEqual(sale.items.get().cmv,old_cmv)
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,8)
        self.assertEqual(StockMovement.objects.count(),count+1)
        totals=sales_summary(Sale.objects.all());self.assertEqual(totals['count'],1)
        self.assertEqual(totals['fees'],D('20.81'));self.assertEqual(totals['contribution'],sale.contribution)
        self.client.force_login(self.actor)
        dashboard=self.client.get(reverse('dashboard'))
        self.assertEqual(dashboard.context['totals']['fees'],D('20.81'))
        self.assertEqual(dashboard.context['totals']['contribution'],sale.contribution)
        self.recover(sale,key=key,revision=revision)
        self.assertEqual(StockMovement.objects.count(),count+1)
        with self.assertRaises(ValidationError):self.recover(sale,key=key,revision=revision,fees=D('10'))
        sale=cancel(actor=self.actor,sale_id=sale.pk,reason='Teste de novo cancelamento')
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,10)
        sale=self.recover(sale)
        self.assertEqual(SaleRecovery.objects.count(),2)
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,8)
        self.assertFalse(FinancialTitle.objects.exists())

    def test_recovery_can_use_known_cost_with_negative_stock(self):
        from apps.inventory.services import execute
        sale=self.cancelled()
        execute(actor=self.actor,key=uuid4(),kind='ISSUE',date=sale.date,reason='Uso posterior',product_id=self.product.pk,location_id=self.location.pk,quantity=D('10'))
        count=StockMovement.objects.count()
        self.recover(sale)
        sale.refresh_from_db();self.assertEqual(sale.status,'CONFIRMED');self.assertEqual(sale.fees,D('20.81'))
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,-2)
        self.assertTrue(SaleRecovery.objects.exists());self.assertEqual(StockMovement.objects.count(),count+1)

    def test_permissions_stale_revision_and_financial_history_block(self):
        sale=self.cancelled()
        with self.assertRaises(PermissionDenied):self.recover(sale,actor=self.operator)
        with self.assertRaises(ValidationError):self.recover(sale,revision=sale.revision-1)
        FinancialTitle.objects.create(direction='RECEIVE',description='Histórico',date=sale.date,due_date=sale.date,amount=100,actor=self.actor,sale=sale,source='sale')
        with self.assertRaises(ValidationError):self.recover(sale)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('sale_recover',args=[sale.pk])).status_code,403)
        self.assertFalse(SaleRecovery.objects.exists())

    def test_bling_link_remains_and_discrepancy_blocks(self):
        from apps.integrations.models import BlingConnection, InvoiceImport
        sale=self.cancelled();connection_obj=BlingConnection.objects.create(pk=1,issuer='00000000000000')
        imported=InvoiceImport.objects.create(connection=connection_obj,external_id='synthetic-recovery',number=sale.invoice_number,series=sale.invoice_series,issued_on=sale.date,source_status='5',source={},fingerprint='test',status='IMPORTED',sale=sale,discrepancy=True)
        with self.assertRaises(ValidationError):self.recover(sale)
        imported.discrepancy=False;imported.source_status='6';imported.save(update_fields=['discrepancy','source_status'])
        self.recover(sale);imported.refresh_from_db()
        self.assertEqual(imported.sale_id,sale.pk);self.assertEqual(imported.status,'IMPORTED')

    @skipUnless(connection.vendor=='postgresql','PostgreSQL trigger')
    def test_database_protection_remains_without_matching_recovery(self):
        sale=self.cancelled()
        with self.assertRaises(DatabaseError),transaction.atomic():Sale.objects.filter(pk=sale.pk).update(fees=D('20.81'))
        with self.assertRaises(DatabaseError),transaction.atomic():Sale.objects.filter(pk=sale.pk).update(status='CONFIRMED')
        self.recover(sale)
        with self.assertRaises(DatabaseError),transaction.atomic():SaleRecovery.objects.update(after_fees=D('1'))
        with self.assertRaises(DatabaseError),transaction.atomic():SaleRecovery.objects.all().delete()
