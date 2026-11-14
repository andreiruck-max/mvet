from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
from django.test import TestCase
from apps.sales.taxes import change_rate
from apps.sales.models import SaleCorrection
from .tests import Fixture
from . import services as s
from .models import Entry, Payment, Allocation


class ProfitCommissionTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.payee.kind='PARTNER_PROFIT'
        self.payee.save()

    def tax(self, rate, start=None):
        latest=self.rule.changes.order_by('-pk').first()
        return change_rate(actor=self.actor,rule_id=self.rule.pk,rate=D(rate),
            effective_from=start or self.today,base='REVENUE',reason='Alíquota corrigida',revision=latest.pk if latest else 0)

    def test_profit_excludes_own_commission_and_equal_installments_conserve_cents(self):
        before=self.sale.contribution+self.sale.commission
        plan=self.plan(installments=[(self.today,D('300')),(self.today,D('650'))])
        self.assertEqual(plan.basis,'PROFIT')
        self.assertEqual(plan.base,D('877.50'))
        self.assertEqual(plan.total,D('43.88'))
        self.assertEqual([i.forecast for i in plan.installments.all()],[D('21.94'),D('21.94')])
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.contribution,before-plan.total)
        self.receipt(plan,'300');self.receipt(plan,'650',index=1)
        self.assertEqual(s.total(Entry.objects.all(),'released'),plan.total)
        self.assertEqual(Entry.objects.first().terms['basis'],'PROFIT')

    def test_tax_changes_paid_plan_create_positive_negative_adjustments_without_rewriting_payment(self):
        plan=self.plan();self.receipt(plan);self.receipt(plan,index=1)
        paid=self.payment(str(plan.total))
        allocations=list(Allocation.objects.values_list('pk','amount'))
        old_events=list(Entry.objects.values_list('pk','released','terms'))
        _,count=self.tax('10');self.assertEqual(count,1)
        plan.refresh_from_db();self.sale.refresh_from_db()
        self.assertEqual(plan.base,D('830.00'));self.assertEqual(plan.total,D('41.50'))
        self.assertEqual(self.sale.commission,plan.total)
        self.assertEqual(s.balance(self.payee),D('-2.38'))
        self.assertIn('Alteração da alíquota de imposto período',Entry.objects.last().command.reason)
        self.tax('0');plan.refresh_from_db()
        self.assertEqual(plan.total,D('46.25'));self.assertEqual(s.balance(self.payee),D('2.37'))
        paid.refresh_from_db();self.assertEqual(paid.amount,D('43.88'));self.assertEqual(Payment.objects.count(),1)
        self.assertEqual(list(Allocation.objects.values_list('pk','amount')),allocations)
        for pk,amount,terms in old_events:
            event=Entry.objects.get(pk=pk);self.assertEqual((event.released,event.terms),(amount,terms))
        events=Entry.objects.count();self.tax('0');self.assertEqual(Entry.objects.count(),events)

    def test_unreceived_plan_revalues_forecast_without_releasing_payment(self):
        plan=self.plan();self.tax('10');plan.refresh_from_db()
        self.assertEqual(plan.total,D('41.50'));self.assertFalse(Entry.objects.exists())

    def test_manual_total_is_preserved_and_loss_earns_zero(self):
        plan=self.plan(override_total=D('30'));self.tax('100');plan.refresh_from_db()
        self.assertEqual(plan.base,0);self.assertEqual(plan.total,30)
        s.adjust(actor=self.actor,plan_id=plan.pk,revision=plan.revision,rate=D('5'),override_total=None,key=uuid4(),reason='Retirar valor fixo')
        plan.refresh_from_db();self.assertEqual(plan.total,0)

    def test_cancel_paid_plan_compensates_and_recovery_restores(self):
        from apps.sales.services import cancel
        from apps.sales.recovery import recover_sale
        plan=self.plan();self.receipt(plan);self.receipt(plan,index=1);self.payment(str(plan.total))
        self.sale.refresh_from_db()
        cancel(actor=self.actor,sale_id=self.sale.pk,reason='Devolução integral da NF')
        self.assertEqual(s.balance(self.payee),-plan.total)
        self.assertIn('Devolução integral',Entry.objects.last().command.reason)
        self.sale.refresh_from_db()
        recover_sale(actor=self.actor,sale_id=self.sale.pk,revision=self.sale.revision,key=uuid4(),reason='Cancelamento incorreto',fees=self.sale.fees)
        self.assertEqual(s.balance(self.payee),0)

    def test_category_change_is_explicit_and_audited_for_existing_plans(self):
        self.payee.kind='PARTNER';self.payee.save();plan=self.plan()
        self.assertEqual(plan.basis,'PRODUCTS');self.assertEqual(plan.total,45)
        self.receipt(plan);self.receipt(plan,index=1);self.payment('45')
        s.configure(actor=self.actor,pk=self.payee.pk,data=dict(name=self.payee.name,kind='PARTNER_PROFIT',user=self.employee,default_rate=D('5'),active=True))
        plan.refresh_from_db();self.assertEqual(plan.basis,'PROFIT');self.assertEqual(plan.total,D('43.88'))
        self.assertEqual(s.balance(self.payee),D('-1.12'))
        self.assertTrue(SaleCorrection.objects.filter(sale=self.sale,reason__contains='categoria').exists())

    def test_effective_period_excludes_sales_before_start(self):
        plan=self.plan();self.tax('20',self.today+timedelta(days=1));plan.refresh_from_db()
        self.assertEqual(plan.total,D('43.88'))
        self.tax('10',self.today-timedelta(days=1));plan.refresh_from_db()
        self.assertEqual(plan.total,D('41.50'))

    def test_cost_correction_rebalances_and_retry_is_idempotent(self):
        from apps.sales.cost_corrections import correct_cost
        plan=self.plan();self.receipt(plan);self.receipt(plan,index=1)
        self.sale.refresh_from_db();revision=self.sale.revision;key=uuid4()
        args=dict(actor=self.actor,sale_id=self.sale.pk,revision=revision,key=key,reason='Custo conferido',costs={self.sale.items.get().pk:D('10')})
        correct_cost(**args);plan.refresh_from_db()
        self.assertEqual(plan.total,D('43.38'))
        count=Entry.objects.count();correct_cost(**args)
        self.assertEqual(Entry.objects.count(),count)

    def test_three_equal_commissions_and_partial_receipt_conserve_cents(self):
        plan=self.plan(installments=[(self.today,D('100')),(self.today,D('350')),(self.today,D('500'))])
        self.assertEqual([i.forecast for i in plan.installments.all()],[D('14.63'),D('14.62'),D('14.63')])
        self.receipt(plan,'25');self.assertEqual(s.balance(self.payee),D('3.66'))
        self.receipt(plan,'75');self.receipt(plan,'350',index=1);self.receipt(plan,'500',index=2)
        self.assertEqual(s.balance(self.payee),plan.total)

    def test_recovery_with_changed_fees_revalues_profit_and_preserves_retry(self):
        from apps.sales.services import cancel
        from apps.sales.recovery import recover_sale
        plan=self.plan();self.receipt(plan);self.receipt(plan,index=1)
        cancel(actor=self.actor,sale_id=self.sale.pk,reason='Cancelamento incorreto')
        self.sale.refresh_from_db()
        args=dict(actor=self.actor,sale_id=self.sale.pk,revision=self.sale.revision,key=uuid4(),reason='Recuperar e conferir taxas',fees=D('13'))
        recover_sale(**args);plan.refresh_from_db()
        self.assertEqual(plan.total,D('43.38'));self.assertEqual(s.balance(self.payee),plan.total)
        count=Entry.objects.count();recover_sale(**args);self.assertEqual(Entry.objects.count(),count)
