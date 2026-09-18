from decimal import Decimal as D
from uuid import uuid4
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.finance.models import FinancialTitle
from apps.reporting.selectors import sales_summary
from apps.reporting.datasets import sales_dataset, build
from .tests import Fixture
from .models import Sale
from .services import save_draft, confirm, cancel, EDIT_FIELDS
from .forms import SaleForm


class ManualMasterTests(Fixture, TestCase):
    def test_master_empty_draft_and_confirmation_require_inventory_context(self):
        draft=save_draft(actor=self.actor,key=uuid4(),data={},items=[])
        self.assertEqual(draft.status,'DRAFT');self.assertEqual(draft.tax_override,0)
        self.assertEqual(draft.invoice_number,'');self.assertIsNone(draft.channel)
        self.assertIsNone(draft.location);self.assertEqual(draft.date,timezone.localdate())
        with self.assertRaises(ValidationError):confirm(actor=self.actor,sale_id=draft.pk,revision=draft.revision)
        self.assertFalse(FinancialTitle.objects.exists())

    def test_master_form_all_business_fields_can_be_empty(self):
        form=SaleForm({'key':str(uuid4()),'revision':0},actor=self.actor)
        self.assertTrue(form.is_valid(),form.errors)
        draft=save_draft(actor=self.actor,key=form.cleaned_data['key'],data={k:form.cleaned_data[k] for k in EDIT_FIELDS},items=[])
        self.assertEqual(draft.products_amount,0);self.assertEqual(draft.tax_override,0)

    def test_multiple_sales_without_nf_are_independent_and_tax_zero(self):
        for _ in range(2):
            data=self.data(invoice_number='',invoice_series='',tax_rule=None,tax_override=D('0'),tax_reason='')
            draft=save_draft(actor=self.actor,key=uuid4(),data=data,items=[(self.product.pk,D('1'))])
            sale=confirm(actor=self.actor,sale_id=draft.pk,revision=draft.revision)
            self.assertEqual(sale.tax_amount,0);self.assertEqual(sale.cmv,5)
            self.assertIn('sem NF',sale.reference)
        self.assertEqual(Sale.objects.count(),2);self.assertEqual(FinancialTitle.objects.count(),2)
        self.assertNotEqual(*[s.reference for s in Sale.objects.all()])

    def test_nonmaster_cannot_inject_adjustment(self):
        with self.assertRaises(PermissionDenied):
            save_draft(actor=self.operator,key=uuid4(),data=self.data(revenue_adjustment=D('50')),items=[(self.product.pk,D('1'))])
        self.assertFalse(Sale.objects.exists())

    def test_master_net_adjustment_matches_title_reports_and_exports(self):
        data=self.data(invoice_number='',tax_rule=None,tax_override=D('0'),tax_reason='',revenue_adjustment=D('-15'))
        draft=save_draft(actor=self.actor,key=uuid4(),data=data,items=[(self.product.pk,D('2'))])
        sale=confirm(actor=self.actor,sale_id=draft.pk,revision=draft.revision)
        self.assertEqual(sale.revenue,80);self.assertEqual(sale.contribution,53)
        self.assertEqual(FinancialTitle.objects.get(sale=sale).amount,80)
        metrics=sales_summary(Sale.objects.all());self.assertEqual(metrics['revenue'],80);self.assertEqual(metrics['contribution'],53)
        period={'start':sale.date,'end':sale.date,'status':'CONFIRMED'}
        export=sales_dataset(self.actor,period)
        self.assertEqual(export.rows[0][export.headers.index('TOTAL')],80)
        self.assertEqual(export.rows[0][export.headers.index('AJUSTE GERENCIAL DA RECEITA')],-15)
        dre=build('dre',self.actor,{'start':str(sale.date),'end':str(sale.date)})
        self.assertIn(('Ajuste gerencial da receita',D('-15')),dre.rows)
        cancel(actor=self.actor,sale_id=sale.pk,reason='Correção local')
        sale.refresh_from_db();self.assertEqual(sale.revenue_adjustment,-15)

    def test_target_form_calculates_audited_adjustment(self):
        values={k: str(v.pk if hasattr(v,'pk') else v) if v is not None else '' for k,v in self.data().items()}
        values.update(key=str(uuid4()),revision=0,revenue_target='80',tax_override='0',tax_reason='')
        form=SaleForm(values,actor=self.actor)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['revenue_adjustment'],-15)
        self.assertTrue(form.cleaned_data['revenue_adjustment_reason'])

    def test_negative_final_revenue_remains_invalid(self):
        with self.assertRaises(ValidationError):
            save_draft(actor=self.actor,key=uuid4(),data=self.data(revenue_adjustment=D('-200')),items=[])

    def test_master_can_submit_empty_ui_draft(self):
        self.client.force_login(self.actor)
        response=self.client.post(reverse('sale_new'),{'key':str(uuid4()),'revision':'0','form-TOTAL_FORMS':'1','form-INITIAL_FORMS':'0','extras-TOTAL_FORMS':'0','extras-INITIAL_FORMS':'0'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Sale.objects.get().invoice_number,'')
