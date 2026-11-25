from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal as D
from threading import Barrier
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from apps.accounts.company_context import CompanyScope
from apps.accounts.models import AccessPolicy
from apps.finance.models import FinancialEntry, FinancialTitle
from apps.inventory.models import StockMovement
from .services import confirm_and_receive
from .tests import Fixture


class DirectReceiptTests(Fixture, TestCase):
    def test_source_amount_stock_and_actual_date_survive_repeat(self):
        purchase = self.draft(external_freight=D('6.25'))
        args = dict(actor=self.buyer,purchase_id=purchase.pk,date=self.date,revision=purchase.revision)
        confirm_and_receive(**args);confirm_and_receive(**args)
        self.assertEqual(list(StockMovement.objects.values_list('company_id','quantity','value')),[(1,10,D('56.25'))])
        self.assertEqual(list(FinancialTitle.objects.values_list('company_id','amount')),[(1,50)])
        self.assertFalse(FinancialEntry.objects.exists())
        with self.assertRaisesMessage(ValidationError,'já foi recebida'):
            confirm_and_receive(**dict(args,date=self.date-timedelta(days=1)))
        purchase.refresh_from_db()
        self.assertEqual(purchase.received_date,self.date)

    def test_failure_and_stale_revision_leave_no_financial_or_stock_postings(self):
        purchase = self.draft()
        for date,revision in [(self.date-timedelta(days=1),purchase.revision),(self.date,purchase.revision-1)]:
            with self.assertRaises(ValidationError):
                confirm_and_receive(actor=self.admin,purchase_id=purchase.pk,date=date,revision=revision)
            purchase.refresh_from_db()
            self.assertEqual((purchase.status,purchase.revision,purchase.receipt_id),('DRAFT',1,None))
            self.assertFalse(FinancialTitle.objects.exists())
            self.assertFalse(StockMovement.objects.exists())

    def test_permission_or_group_cannot_complete_or_replay(self):
        purchase=self.draft()
        url=reverse('purchase_confirm_receive',args=[purchase.pk])
        payload={'date':self.date,'revision':purchase.revision}
        AccessPolicy.objects.create(user=self.buyer,rules={'core.receive_purchases':False})
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.post(url,payload).status_code,403)
        self.assertNotContains(self.client.get(reverse('purchase_detail',args=[purchase.pk])),'Confirmar compra e recebimento')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code,405)
        confirm_and_receive(actor=self.admin,purchase_id=purchase.pk,**payload)
        self.admin._mvet_company_scope=CompanyScope((1,),group=True)
        with self.assertRaises(PermissionDenied):
            confirm_and_receive(actor=self.admin,purchase_id=purchase.pk,**payload)


class ConcurrentDirectReceiptTests(Fixture, TransactionTestCase):
    def test_two_confirmations_of_same_draft_post_once(self):
        purchase=self.draft()
        barrier=Barrier(2,timeout=15)
        def post():
            try:
                actor=User.objects.get(pk=self.admin.pk)
                barrier.wait()
                return confirm_and_receive(actor=actor,purchase_id=purchase.pk,date=self.date,revision=purchase.revision).receipt_id
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(post) for _ in range(2)]
            receipts=[f.result(timeout=30) for f in futures]
        self.assertIsNotNone(receipts[0])
        self.assertEqual(receipts[0],receipts[1])
        self.assertEqual((FinancialTitle.objects.count(),StockMovement.objects.count(),FinancialEntry.objects.count()),(1,1,0))
