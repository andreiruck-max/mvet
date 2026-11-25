from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.company_context import CompanyScope
from apps.accounts.models import UserCompanyAccess
from apps.core.models import AuditLog, Company
from .models import Sale, SaleTaxRevision, TaxRateChange, TaxRule
from .services import save_configuration
from .taxes import change_rate, effective_terms
from .tests import Fixture


@override_settings(COMPANY_CONTEXT_ENABLED=True)
class CompanyTaxSetupTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.agro, _ = Company.objects.get_or_create(pk=2, defaults={'active':False, 'name':'Agro teste'})
        self.today = timezone.localdate()
        self.url = reverse('company_tax_rules', args=[self.agro.pk])
        self.data_rule = dict(name=self.rule.name, rate='4', base='PRODUCTS', starts_on=self.today.isoformat(), active='on')
        self.client.force_login(self.actor)

    def test_create_edit_and_version_secondary_rule_preserve_primary_sale(self):
        sale = self.confirmed()
        original = Sale.objects.values().get(pk=sale.pk)
        self.assertRedirects(self.client.post(self.url, dict(self.data_rule, company_id='1')), self.url)
        secondary = TaxRule.objects.get(company=self.agro)
        self.assertEqual((secondary.name,secondary.rate),(self.rule.name,Decimal('4')))
        self.assertEqual([r.pk for r in self.client.get(self.url).context['page']],[secondary.pk])
        edit_url = reverse('company_tax_rule_edit', args=[2,secondary.pk])
        self.assertRedirects(self.client.post(edit_url, dict(self.data_rule, name='Regra Agro',rate='99')), self.url)
        secondary.refresh_from_db()
        self.assertEqual((secondary.name,secondary.rate),('Regra Agro',Decimal('4')))
        url = reverse('company_tax_change',args=[2,secondary.pk])
        values = dict(rate='6',effective_from=self.today.isoformat(),base='REVENUE',reason='Alteração Agro',revision=0)
        self.assertRedirects(self.client.post(url,values),url)
        self.assertFormError(self.client.post(url,dict(values,rate='9')).context['form'],None,
                             'A regra mudou em outra sessão. Reabra a edição.')
        change = TaxRateChange.objects.get(rule=secondary)
        self.assertEqual((change.company_id,change.rate),(2,Decimal('6')))
        self.assertTrue(AuditLog.objects.filter(operation='change_tax_rate',after__company_id=2).exists())
        self.assertEqual(effective_terms(self.rule,self.today)[0],Decimal('5'))
        self.assertEqual(Sale.objects.values().get(pk=sale.pk),original)
        self.assertFalse(SaleTaxRevision.objects.exists())
        self.assertContains(self.client.get(self.url),'6%')
        self.agro.refresh_from_db()
        self.assertFalse(self.agro.active)

    def test_foreign_rule_unknown_for_get_post_and_future_change_not_displayed_as_current(self):
        for route in ('company_tax_rule_edit','company_tax_change'):
            url = reverse(route,args=[2,self.rule.pk])
            self.assertEqual(self.client.get(url).status_code,404)
            self.assertEqual(self.client.post(url,self.data_rule).status_code,404)
        self.client.post(self.url,self.data_rule)
        rule=TaxRule.objects.get(company_id=2)
        change_rate(actor=self.actor,company_id=2,rule_id=rule.pk,rate=Decimal('7'),
                    effective_from=self.today+timedelta(days=1),base='REVENUE',reason='Futura',revision=0)
        self.assertContains(self.client.get(self.url),'4%')
        self.assertNotContains(self.client.get(self.url),'7%')
        with self.assertRaises(ValidationError):
            save_configuration(actor=self.actor,model=TaxRule,company_id=2,data={'id':self.rule.pk})
        self.assertNotContains(self.client.get(reverse('sales_configuration',args=['impostos'])),
                               reverse('company_tax_change',args=[2,rule.pk]))

    def test_employee_group_and_missing_csrf_cannot_prepare(self):
        UserCompanyAccess.objects.create(user=self.operator,company_id=1,rules={'core.manage_taxes':True})
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('sales_configuration',args=['impostos'])).status_code,200)
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.assertEqual(self.client.post(self.url,self.data_rule).status_code,403)
        with self.assertRaises(PermissionDenied):
            save_configuration(actor=self.operator,model=TaxRule,company_id=2,data={})
        self.client.force_login(self.actor)
        protected=Client(enforce_csrf_checks=True)
        protected.force_login(self.actor)
        self.assertEqual(protected.post(self.url,self.data_rule).status_code,403)
        session=self.client.session
        session['company_selection']='group'
        session.save()
        self.assertEqual(self.client.post(self.url,self.data_rule).status_code,403)
        self.actor._mvet_company_scope=CompanyScope((1,),group=True)
        with self.assertRaises(PermissionDenied):
            save_configuration(actor=self.actor,model=TaxRule,company_id=2,data={})
        self.assertFalse(TaxRule.objects.filter(company_id=2).exists())

    @override_settings(COMPANY_CONTEXT_ENABLED=False)
    def test_off_in_legacy_mode(self):
        self.assertEqual(self.client.get(self.url).status_code,404)
        with self.assertRaises(PermissionDenied):
            save_configuration(actor=self.actor,model=TaxRule,company_id=2,data={})
