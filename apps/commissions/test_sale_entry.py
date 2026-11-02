from decimal import Decimal as D
from uuid import uuid4
from django.test import TestCase
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth.models import Permission
from apps.sales.tests import Fixture
from apps.sales import services as sales
from apps.sales.models import Sale, SalesChannel
from apps.sales.forms import SaleForm
from apps.inventory.models import StockOperation
from apps.finance.models import FinancialTitle
from .models import Payee, CommissionPlan, CommissionSettings, Entry
from . import services as commissions


class SaleEntryCommissionTests(Fixture,TestCase):
    def setUp(self):
        super().setUp()
        self.payee=Payee.objects.create(name='Vendedor sintético',default_rate=D('5'))
        self.channel.commission_payee=self.payee;self.channel.save()

    def test_channel_default_customer_cost_idempotence_and_no_release(self):
        sale=self.confirmed(commission=D(0),customer_name='Cliente manual',discount=D(10),shipping_received=D(5))
        plan=sale.commission_plan
        self.assertEqual(plan.payee,self.payee);self.assertEqual(plan.customer,'Cliente manual')
        self.assertEqual(plan.total,D('4.50'));self.assertEqual(sale.commission,D('4.50'))
        self.assertEqual(plan.installments.get().amount,D('95'))
        self.assertEqual(plan.installments.get().due_date,sale.date)
        self.assertEqual(Entry.objects.count(),0);self.assertEqual(FinancialTitle.objects.count(),0)
        sales.confirm(actor=self.operator,sale_id=sale.pk,revision=sale.revision)
        commissions.create_from_confirmed_sale(actor=self.operator,sale=sale)
        self.assertEqual(CommissionPlan.objects.count(),1)
        self.assertFalse(self.operator.has_perm('core.manage_commissions'))

    def test_manual_zero_and_explicit_payee_override(self):
        other=Payee.objects.create(name='Outro vendedor',default_rate=D(20))
        sale=self.confirmed(commission=D(0),commission_payee=other,commission_manual_total=D('7.33'))
        self.assertEqual(sale.commission_plan.payee,other)
        self.assertEqual(sale.commission_plan.total,D('7.33'))
        self.assertEqual(sale.commission,D('7.33'))
        zero=self.confirmed(invoice_number='101',commission_manual_total=D(0))
        self.assertEqual(zero.commission_plan.total,0);self.assertEqual(zero.commission,0)

    def test_missing_rate_and_inactive_payee_roll_back_confirmation(self):
        self.payee.default_rate=None;self.payee.save()
        draft=self.draft(commission=D(0));before=StockOperation.objects.count()
        with self.assertRaises(ValidationError):sales.confirm(actor=self.operator,sale_id=draft.pk,revision=draft.revision)
        draft.refresh_from_db();self.assertEqual(draft.status,'DRAFT')
        self.assertEqual(StockOperation.objects.count(),before)
        CommissionSettings.objects.create(pk=1,default_rate=D(3))
        sale=sales.confirm(actor=self.operator,sale_id=draft.pk,revision=draft.revision)
        self.assertEqual(sale.commission_plan.total,D('2.70'))
        self.payee.active=False;self.payee.save()
        draft=self.draft(invoice_number='102',commission=D(0))
        with self.assertRaises(ValidationError):sales.confirm(actor=self.operator,sale_id=draft.pk,revision=draft.revision)
        self.assertEqual(CommissionPlan.objects.count(),1)

    def test_manual_form_blank_uses_default_and_clear_resets_override(self):
        legacy=self.draft(commission=D('12'))
        self.assertEqual(SaleForm(instance=legacy,actor=self.actor).initial['commission_manual_total'],D('12'))
        data={k:(v.pk if hasattr(v,'pk') else v) for k,v in self.data().items() if v is not None}
        data.update(key=str(uuid4()),revision=0,invoice_number='202',customer_name='Cliente formulário',commission_manual_total='',commission_payee='',commission='12')
        form=SaleForm(data=data,actor=self.actor)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['commission'],0)
        self.assertIsNone(form.cleaned_data['commission_manual_total'])
        self.assertIn('customer_name',[f.name for f in form.basic_fields])
        data['commission_manual_total']='0'
        form=SaleForm(data=data,actor=self.actor);self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data['commission_manual_total'],0)

    def test_bling_copies_customer_and_generates_plan(self):
        from apps.integrations.models import BlingConnection
        from apps.integrations.tests import payload,ISSUER
        from apps.integrations.services import stage,approve
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        invoice=stage(actor=self.actor,connection=connection,payload=payload(contato={'nome':'Cliente Bling'}))
        sale=approve(actor=self.actor,invoice_id=invoice.pk,revision=invoice.revision,data=self.data(commission=D(0),customer_name='Não usar este nome',commission_manual_total=D('8')),extra_costs=[],reviewed=True)
        self.assertEqual(sale.customer_name,'Cliente Bling')
        self.assertEqual(sale.commission_plan.customer,'Cliente Bling')
        self.assertEqual(sale.commission_plan.total,8)
        repeated=approve(actor=self.actor,invoice_id=invoice.pk,revision=invoice.revision,data={},extra_costs=[],reviewed=True)
        self.assertEqual(repeated.pk,sale.pk);self.assertEqual(CommissionPlan.objects.count(),1)

    def test_mapping_requires_management_and_seed_is_exact_idempotent(self):
        self.operator.user_permissions.add(Permission.objects.get(codename='manage_channels'))
        with self.assertRaises(PermissionDenied):sales.save_configuration(actor=self.operator,model=SalesChannel,pk=self.channel.pk,data={'commission_payee':None})
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        migration=import_module('apps.sales.migrations.0016_link_seller_commissions')
        cesar=Payee.objects.create(name='César Oliveira',default_rate=D(2))
        lucas=Payee.objects.create(name='Lucas Abranches',default_rate=D(3))
        c=SalesChannel.objects.create(name='[VENDEDOR] CESAR');l=SalesChannel.objects.create(name='[VENDEDOR] LUCAS')
        with connection.schema_editor(atomic=False) as editor:migration.link_existing(apps,editor)
        c.refresh_from_db();l.refresh_from_db()
        self.assertEqual(c.commission_payee,cesar);self.assertEqual(l.commission_payee,lucas)
        with connection.schema_editor(atomic=False) as editor:migration.link_existing(apps,editor)
        self.assertEqual(CommissionPlan.objects.count(),0)
