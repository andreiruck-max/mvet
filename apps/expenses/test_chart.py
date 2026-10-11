from decimal import Decimal as D
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from apps.reporting.selectors import dre
from apps.finance.models import FinancialTitle, FinancialEntry
from .tests import Fixture
from .chart import install_chart
from .models import ChartOfAccount as Category
from . import services


class ChartTests(Fixture, TestCase):
    def test_install_preserves_used_categories_and_is_idempotent(self):
        old=self.expense(category=self.category)
        before=old.category_snapshot
        self.assertGreater(install_chart(),60)
        self.assertEqual(install_chart(),0)
        old.refresh_from_db();self.assertEqual(old.category_snapshot,before)
        self.category.refresh_from_db();self.assertEqual(self.category.name,'Contabilidade')
        for category in Category.objects.filter(seed_key__isnull=False):
            self.assertTrue(services.category_path(category,expense=False))
        principal=Category.objects.get(seed_key='mercadovet-2026:90.04')
        self.assertEqual(principal.nature,'LIABILITY')
        with self.assertRaises(ValidationError): self.expense(category=principal)

    def test_depreciation_affects_result_without_payable_or_bank_and_cancels(self):
        install_chart()
        category=Category.objects.get(seed_key='mercadovet-2026:08.01')
        expense=self.expense(category=category)
        self.assertIsNone(expense.title_id)
        self.assertEqual(FinancialTitle.objects.count(),0)
        self.assertEqual(FinancialEntry.objects.count(),0)
        report=dre({'start':self.today,'end':self.today})
        self.assertEqual(report['ebitda'],D('0'))
        self.assertEqual(report['result'],D('-100'))
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('expense_detail',args=[expense.pk])).status_code,200)
        with self.assertRaises(ValidationError):
            services.reclassify(actor=self.admin,pk=expense.pk,category=self.category,cost_center='',reason='Trocar',revision=expense.revision)
        services.cancel_expense(actor=self.admin,pk=expense.pk,reason='Corrigir competência')
        self.assertEqual(dre({'start':self.today,'end':self.today})['result'],D('0'))

    def test_pending_category_does_not_silently_enter_operating_result(self):
        install_chart();self.expense(category=Category.objects.get(seed_key='mercadovet-2026:99.01'))
        report=dre({'start':self.today,'end':self.today})
        self.assertTrue(report['provisional']);self.assertEqual(report['expenses']['NONE'],D('100'))
        self.assertEqual(report['ebitda'],D('0'))
