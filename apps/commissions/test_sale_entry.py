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

    def test_manual_terms_survive_draft_and_allocate_commission_without_receivable(self):
        from datetime import timedelta
        day=self.data()['date'];terms=[{'due_date':str(day+timedelta(days=30)),'amount':'30.00'},{'due_date':str(day+timedelta(days=60)),'amount':'65.00'}]
        key=uuid4()
        draft=sales.save_draft(actor=self.operator,key=key,data=self.data(commission_manual_total=D('7.33')),items=[(self.product.pk,D(2))],commission_installments=terms)
        same=sales.save_draft(actor=self.operator,key=key,data=self.data(commission_manual_total=D('7.33')),items=[(self.product.pk,D(2))],commission_installments=terms)
        self.assertEqual(same.pk,draft.pk)
        changed=[dict(terms[0],due_date=str(day+timedelta(days=31))),terms[1]]
        with self.assertRaises(ValidationError):
            sales.save_draft(actor=self.operator,key=key,data=self.data(commission_manual_total=D('7.33')),items=[(self.product.pk,D(2))],commission_installments=changed)
        draft=sales.save_draft(actor=self.operator,key=uuid4(),data=self.data(commission_manual_total=D('7.33')),items=[(self.product.pk,D(2))],sale_id=draft.pk,revision=draft.revision)
        self.assertEqual(draft.commission_installments,terms)
        sale=sales.confirm(actor=self.operator,sale_id=draft.pk,revision=draft.revision)
        rows=list(sale.commission_plan.installments.all())
        self.assertEqual([str(r.due_date) for r in rows],[t['due_date'] for t in terms])
        self.assertEqual([r.amount for r in rows],[D(30),D(65)])
        self.assertEqual(sum(r.forecast for r in rows),D('7.33'))
        self.assertFalse(FinancialTitle.objects.exists());self.assertFalse(Entry.objects.exists())

    def test_invalid_terms_do_not_save_sale(self):
        from datetime import timedelta
        day=self.data()['date']
        for terms in [
            [{'due_date':str(day),'amount':'94.99'}],
            [{'due_date':str(day-timedelta(days=1)),'amount':'95'}],
            [{'due_date':str(day),'amount':'0'}],
            [{'due_date':str(day),'amount':'95.001'}],
            [{'due_date':str(day),'amount':'NaN'}],
            [{'due_date':'bad','amount':'95'}],
            [{'due_date':str(day),'amount':'95'}]*61,
        ]:
            with self.subTest(terms=terms),self.assertRaises(ValidationError):
                sales.save_draft(actor=self.operator,key=uuid4(),data=self.data(),items=[(self.product.pk,D(2))],commission_installments=terms)
        self.assertFalse(Sale.objects.exists())

    def test_bling_installment_dates_and_amounts_are_preserved(self):
        from datetime import timedelta
        from apps.integrations.models import BlingConnection
        from apps.integrations.tests import payload,ISSUER
        from apps.integrations.services import stage,approve
        day=self.data()['date'];dates=[day+timedelta(days=n) for n in (30,60,90)]
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        invoice=stage(actor=self.actor,connection=connection,payload=payload(parcelas=[{'data':str(d),'valor':v} for d,v in zip(dates,['33.33','33.33','33.34'])]))
        sale=approve(actor=self.actor,invoice_id=invoice.pk,revision=invoice.revision,data=self.data(discount=D(0),shipping_received=D(0)),extra_costs=[],reviewed=True)
        rows=list(sale.commission_plan.installments.all())
        self.assertEqual([r.due_date for r in rows],dates)
        self.assertEqual([r.amount for r in rows],[D('33.33'),D('33.33'),D('33.34')])
        self.assertFalse(FinancialTitle.objects.exists());self.assertFalse(Entry.objects.exists())

    def test_blank_schedule_reason_is_audited_and_other_actions_still_require_reason(self):
        from datetime import timedelta
        from .forms import ScheduleActionForm,ReceiptForm
        from .models import Command
        plan=self.confirmed().commission_plan;item=plan.installments.get()
        form=ScheduleActionForm({'key':str(uuid4()),'revision':plan.revision,'reason':''})
        self.assertTrue(form.is_valid(),form.errors)
        self.assertFalse(ReceiptForm({'key':str(uuid4()),'date':str(self.data()['date']),'amount':'1','reason':''}).is_valid())
        key=form.cleaned_data['key']
        kwargs=dict(actor=self.actor,plan_id=plan.pk,revision=plan.revision,rows=[{'installment_id':item.pk,'due_date':item.due_date+timedelta(days=30),'amount':item.amount}],key=key,reason='')
        commissions.revise_schedule(**kwargs);commissions.revise_schedule(**kwargs)
        item.refresh_from_db();self.assertEqual(item.due_date,plan.sale.date+timedelta(days=30))
        cmd=Command.objects.get(key=key)
        self.assertEqual(cmd.reason,'Cronograma de comissão atualizado.')
        self.assertEqual(cmd.actor,self.actor);self.assertTrue(cmd.before['schedule'])
        from apps.core.models import AuditLog
        log=AuditLog.objects.get(operation='commission_schedule',entity_id=str(plan.pk))
        self.assertTrue(log.after['schedule']);self.assertEqual(log.after['reason'],cmd.reason)


    def test_empty_terms_do_not_change_legacy_or_purchase_source(self):
        from apps.integrations.tests import payload,ISSUER
        from apps.integrations.normalization import normalize
        self.assertNotIn('commission_installments',normalize(payload(),ISSUER))
        self.assertNotIn('commission_installments',normalize(payload(tipo=0,parcelas=[{'data':'2026-12-01','valor':'100'}]),ISSUER))
