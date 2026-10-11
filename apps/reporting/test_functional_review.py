"""Cross-screen regressions found during the functional review (synthetic data)."""
from datetime import timedelta
from decimal import Decimal as D
from io import BytesIO
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from django.test import TestCase
from django.urls import reverse
from apps.finance import services as finance, selectors as cash
from apps.purchases import selectors as purchases
from apps.purchases.models import PurchaseInstallment
from .tests import ReportingFixture
from .datasets import build
from .files import xlsx, NS


class FunctionalReviewTests(ReportingFixture, TestCase):
    def test_rescheduled_installment_uses_same_date_in_filters_detail_supplier_and_export(self):
        purchase=self.purchase()
        installment=purchase.installments.first()
        new_date=self.today+timedelta(days=45)
        title=installment.financial_title
        finance.schedule_title(actor=self.actor,pk=title.pk,due_date=new_date,
                               account=self.account,notes='Renegociação sintética',revision=title.revision)
        installment.refresh_from_db()
        self.assertEqual(installment.due_date,self.today)  # Contractual history remains untouched.
        self.assertEqual(installment.effective_due_date,new_date)
        self.assertFalse(purchases.purchases({'due_start':self.today,'due_end':self.today}).exists())
        self.assertEqual(list(purchases.purchases({'due_start':new_date,'due_end':new_date})),[purchase])
        _,_,outstanding=purchases.supplier_report(purchase.supplier)
        self.assertEqual([i.number for i in outstanding],[2,1])
        for kind in ('purchases','payables'):
            query={'period':'all'} if kind=='payables' else {}
            dataset=build(kind,self.actor,query)
            self.assertEqual([r[4] for r in dataset.rows],[self.today+timedelta(days=30),new_date])
        self.client.force_login(self.actor)
        response=self.client.get(reverse('purchase_detail',args=[purchase.pk]))
        self.assertContains(response,new_date.strftime('%d/%m/%Y'))
        self.assertContains(response,'Original: '+self.today.strftime('%d/%m/%Y'))
        draft=PurchaseInstallment(purchase=purchase,number=3,due_date=self.today,amount=D(10))
        self.assertEqual(draft.effective_due_date,self.today)

    def test_rescheduled_away_from_past_not_overdue_in_purchase_search(self):
        purchase=self.purchase();title=purchase.installments.first().financial_title
        finance.schedule_title(actor=self.actor,pk=title.pk,due_date=self.today+timedelta(days=4),account=None,notes='',revision=title.revision)
        with patch('apps.purchases.selectors.timezone.localdate',return_value=self.today+timedelta(days=1)):
            self.assertFalse(purchases.purchases({'pending':'overdue'}).exists())

    def test_cash_export_horizontal_respects_mode_and_future_settlement(self):
        day=self.today+timedelta(days=2)
        title=self.title(due_date=day,amount=D(25));self.pay(title,date=day)
        for mode,expected in [('actual',D(1000)),('projected',D(975))]:
            ds=build('cash',self.actor,{'start':day,'end':day,'mode':mode})
            with ZipFile(BytesIO(xlsx(ds,'Empresa sintética'))) as book:
                root=ET.fromstring(book.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(D(root.find(f'.//{{{NS}}}c[@r="D3"]/{{{NS}}}v').text),expected)
            self.assertEqual(D(root.find(f'.//{{{NS}}}c[@r="C3"]/{{{NS}}}v').text),D(25) if mode=='projected' else D(0))
            self.assertEqual(ds.rows[0][-2:], [D(1000),D(975)])
            self.assertIn('Realizado + previsto' if mode=='projected' else 'Somente realizado',ds.notes)

    def test_cash_page_materializes_ledger_once_and_preserves_totals(self):
        self.title(amount=D(20))
        self.client.force_login(self.actor)
        with patch('apps.finance.selectors.daily_cash',wraps=cash.daily_cash) as calculation:
            response=self.client.get(reverse('finance'),self.period)
        self.assertEqual(calculation.call_count,1)
        self.assertEqual(response.context['summary']['actual'],D(1000))
        self.assertEqual(response.context['summary']['projected'],D(980))

    def test_dashboard_explains_all_account_scope_without_losing_archived_balance(self):
        finance.save_account(actor=self.actor,pk=self.account.pk,data={'active':False})
        self.client.force_login(self.actor)
        response=self.client.get(reverse('dashboard'),self.period)
        self.assertEqual(response.context['cash_today'],D(1000))
        self.assertContains(response,'contas ativas e inativas')
        self.assertEqual(self.client.get(reverse('finance')).context['summary']['actual'],D(0))
