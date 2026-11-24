from decimal import Decimal as D
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from apps.accounts.company_context import CompanyScope
from apps.core.models import Company
from apps.inventory.tests import StockFixtures, DAY
from .models import TaxRule, TaxRateChange, Sale
from .forms import SaleForm
from .services import save_configuration
from .taxes import calculate_tax, suggested_rule, change_rate


@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class IndependentTaxRulesTests(StockFixtures, TestCase):
    def setUp(self):
        super().setUp()
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        self.primary=TaxRule.objects.create(company_id=1,name='Imposto próprio',rate=D('8'),starts_on=DAY,base='REVENUE')
        self.secondary=TaxRule.objects.create(company_id=2,name='Imposto próprio',rate=D('4'),starts_on=DAY,base='REVENUE')

    def sale(self, owner, rule):
        return Sale(company_id=owner,tax_rule=rule,date=DAY,products_amount=D('100'))

    def test_same_name_distinct_rates_and_history_never_mix(self):
        first,second=self.sale(1,self.primary),self.sale(2,self.secondary)
        self.assertEqual(calculate_tax(first)[0],D('8'))
        self.assertEqual(calculate_tax(second)[0],D('4'))
        TaxRateChange.objects.create(company_id=2,rule=self.secondary,rate=D('12'),
            effective_from=DAY,base='REVENUE',reason='Revisão secundária sintética',actor=self.actor)
        self.assertEqual(calculate_tax(first)[0],D('8'))
        self.assertEqual(calculate_tax(second)[0],D('12'))
        self.assertEqual(suggested_rule(DAY,company_id=1),self.primary)
        self.assertEqual(suggested_rule(DAY,company_id=2),self.secondary)
        first.tax_rule=self.secondary
        with self.assertRaisesMessage(ValidationError,'outra empresa'):
            calculate_tax(first)

    def test_primary_forms_and_routes_do_not_expose_secondary_rule(self):
        form=SaleForm(actor=self.actor)
        self.assertNotIn(self.secondary,form.fields['tax_rule'].queryset)
        self.client.force_login(self.actor)
        page=self.client.get(reverse('sales_configuration',args=['impostos']))
        self.assertEqual([rule.pk for rule in page.context['page']], [self.primary.pk])
        for route,args in [('sales_configuration_edit',['impostos',self.secondary.pk]),('tax_change',[self.secondary.pk])]:
            target=reverse(route,args=args)
            self.assertEqual(self.client.get(target).status_code,404)
            self.assertEqual(self.client.post(target,{}).status_code,404)

    def test_service_rejects_cross_owner_edit_and_group_configuration(self):
        with self.assertRaises(TaxRule.DoesNotExist):
            save_configuration(actor=self.actor,model=TaxRule,pk=self.secondary.pk,data={'name':'Tentativa'})
        with self.assertRaises(PermissionDenied):
            change_rate(actor=self.actor,company_id=2,rule_id=self.secondary.pk,
                rate=D('10'),effective_from=DAY,base='REVENUE',reason='Tentativa',revision=0)
        self.actor._mvet_company_scope=CompanyScope((1,),group=True)
        with self.assertRaises(PermissionDenied):
            save_configuration(actor=self.actor,model=TaxRule,pk=self.primary.pk,data={'name':'Tentativa'})
        self.secondary.refresh_from_db()
        self.assertEqual(self.secondary.rate,D('4'))

    def test_database_prevents_owner_reassignment_and_cross_owner_history(self):
        with self.assertRaisesMessage(DatabaseError,'Tax rule owner is immutable'), transaction.atomic():
            TaxRule.objects.filter(pk=self.primary.pk).update(company_id=2)
        with self.assertRaisesMessage(DatabaseError,'Tax rate change owner differs'), transaction.atomic():
            TaxRateChange.objects.create(company_id=1,rule=self.secondary,rate=D('12'),
                effective_from=DAY,base='REVENUE',reason='Tentativa',actor=self.actor)
