from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
from unittest import skipUnless
from django.contrib.auth.models import User,Permission
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import connection,transaction,DatabaseError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture as SalesFixture
from apps.sales import services as sales
from apps.sales.corrections import correct_sale,FIELDS
from apps.sales.recovery import recover_sale
from apps.finance.models import FinancialTitle,FinancialEntry
from . import services as s,selectors as q
from .models import Payee,CommissionPlan,CommissionSettings,Entry,Payment,Allocation,Command

class Fixture(SalesFixture):
    def setUp(self):
        super().setUp()
        self.today=timezone.localdate()
        self.employee=User.objects.create_user('commission_employee')
        self.employee.user_permissions.add(Permission.objects.get(codename='view_own_commissions'))
        self.payee=Payee.objects.create(name='Vendedor sintético',user=self.employee,default_rate=D('5'))
        self.sale=self.confirmed(products_amount=D('1000'),discount=D('100'),shipping_received=D('50'))
    def plan(self,**kw):
        data=dict(actor=self.actor,sale_id=self.sale.pk,payee_id=self.payee.pk,customer='Cliente sintético',rate=None,
            installments=[(self.today,D('475')),(self.today+timedelta(days=30),D('475'))],key=uuid4(),reason='Definição sintética')
        data.update(kw);return s.create_plan(**data)
    def receive(self,*args,**kwargs):
        # Sales fixture uses this helper for stock before commissioning exists.
        return super().receive(*args,**kwargs)
    def receipt(self,plan,amount='475',index=0,date=None,key=None):
        return s.receive(actor=self.actor,installment_id=list(plan.installments.all())[index].pk,amount=D(amount),date=date or self.today,key=key or uuid4(),reason='Recebimento confirmado')
    def payment(self,amount,date=None,**kw):
        data=dict(actor=self.actor,payee_id=self.payee.pk,amount=D(amount),date=date or self.today,period=date or self.today,method='PIX',key=uuid4(),reason='Pagamento realizado')
        data.update(kw);return s.pay(**data)

class CommissionTests(Fixture,TestCase):
    def test_base_excludes_freight_discount_and_cost_uses_single_sale_field(self):
        original=self.sale.contribution;plan=self.plan();self.sale.refresh_from_db()
        self.assertEqual(plan.base,900);self.assertEqual(plan.total,45);self.assertEqual(plan.rate_source,'PAYEE')
        self.assertEqual(self.sale.commission,45);self.assertEqual(self.sale.contribution,original+D('2')-D('45'))
        self.assertFalse(FinancialTitle.objects.filter(sale=self.sale).exists());self.assertFalse(FinancialEntry.objects.exists())
        self.assertEqual(s.total(Entry.objects.all(),'released'),0)

    def test_partial_receipts_and_unequal_allocations_conserve_total(self):
        plan=self.plan(installments=[(self.today,D('300')),(self.today,D('650'))])
        parts=list(plan.installments.all());self.assertEqual(sum(i.forecast for i in parts),45)
        e=self.receipt(plan,'100');self.assertEqual(e.released,D('4.74'))
        self.receipt(plan,'200');self.receipt(plan,'650',index=1)
        p=q.decorate(q.plans(self.actor).get(pk=plan.pk));self.assertEqual(p.released,45);self.assertEqual(p.received_count,2)

    def test_rounding_tiny_repeated_receipts(self):
        plan=self.plan(rate=D('0.0001'))
        self.receipt(plan,'0.01');self.receipt(plan,'474.99');self.receipt(plan,'475',index=1)
        self.assertEqual(s.total(Entry.objects.all(),'released'),plan.total)

    def test_rate_priority_and_future_default_preserves_snapshot(self):
        CommissionSettings.objects.create(pk=1,default_rate=D('3'))
        plan=self.plan(rate=D('7'));self.assertEqual(plan.rate_source,'MANUAL');self.assertEqual(plan.total,63)
        s.configure_default(actor=self.actor,rate=D('9'),reason='Novo padrão');plan.refresh_from_db();self.assertEqual(plan.rate,7)

    def test_global_default_when_person_has_none(self):
        self.payee.default_rate=None;self.payee.save()
        s.configure_default(actor=self.actor,rate=D('4'),reason='Padrão')
        plan=self.plan();self.assertEqual(plan.total,36);self.assertEqual(plan.rate_source,'DEFAULT')

    def test_unconfigured_rate_does_not_silently_replace_sale_cost_with_zero(self):
        self.payee.default_rate=None;self.payee.save()
        with self.assertRaises(ValidationError):self.plan()
        self.sale.refresh_from_db();self.assertEqual(self.sale.commission,2)

    def test_create_and_receipt_replays_do_not_duplicate(self):
        key=uuid4();plan=self.plan(key=key);self.assertEqual(self.plan(key=key).pk,plan.pk)
        key=uuid4();e=self.receipt(plan,key=key);self.assertEqual(self.receipt(plan,key=key).pk,e.pk)
        with self.assertRaises(ValidationError):self.receipt(plan,'10',key=key)
        self.assertEqual(Entry.objects.count(),1)

    def test_cannot_release_unreceived_overreceived_or_future(self):
        plan=self.plan()
        with self.assertRaises(ValidationError):self.payment('1')
        with self.assertRaises(ValidationError):self.receipt(plan,'476')
        with self.assertRaises(ValidationError):self.receipt(plan,date=self.today+timedelta(days=1))
        self.assertFalse(Entry.objects.exists())

    def test_schedule_must_reconcile_and_atomic_rollback(self):
        with self.assertRaises(ValidationError):self.plan(installments=[(self.today,D('900'))])
        self.assertFalse(CommissionPlan.objects.exists());self.assertFalse(Command.objects.exists())
        self.sale.refresh_from_db();self.assertEqual(self.sale.commission,2)

    def test_partial_payment_allocates_exactly_and_replay(self):
        plan=self.plan();self.receipt(plan);key=uuid4()
        payment=self.payment('10',key=key);self.assertEqual(self.payment('10',key=key).pk,payment.pk)
        self.assertEqual(s.total(payment.allocations,'amount'),10);self.assertEqual(s.balance(self.payee),D('12.50'))
        self.assertEqual(Payment.objects.count(),1)

    def test_payment_never_allocates_to_cancelled_credit_from_another_sale(self):
        cancelled=self.plan();self.receipt(cancelled)
        sales.cancel(actor=self.actor,sale_id=self.sale.pk,reason='Cancelamento sem comissão paga')
        sale2=self.confirmed(invoice_number='101',products_amount=D('1000'),discount=D('100'),shipping_received=D('50'))
        live=self.plan(sale_id=sale2.pk);entry=self.receipt(live)
        payment=self.payment('22.50')
        self.assertEqual(payment.allocations.get().entry_id,entry.pk)
        self.assertEqual(q.decorate(q.plans(self.actor).get(pk=cancelled.pk)).pending,0)

    def test_reversed_receipt_cannot_absorb_new_receipt_payment(self):
        plan=self.plan();original=self.receipt(plan)
        s.reverse_receipt(actor=self.actor,entry_id=original.pk,date=self.today,key=uuid4(),reason='Recebimento equivocado')
        actual=self.receipt(plan);payment=self.payment('22.50')
        self.assertEqual(payment.allocations.get().entry_id,actual.pk)

    def test_paid_receipt_reversal_clawback_and_payment_reversal(self):
        plan=self.plan();e=self.receipt(plan);p=self.payment('22.50')
        s.reverse_receipt(actor=self.actor,entry_id=e.pk,date=self.today,key=uuid4(),reason='Recebimento desfeito')
        self.assertEqual(s.balance(self.payee),D('-22.50'))
        with self.assertRaises(ValidationError):self.payment('0.01')
        s.reverse_payment(actor=self.actor,payment_id=p.pk,date=self.today,key=uuid4(),reason='Valor devolvido')
        self.assertEqual(s.balance(self.payee),0);self.assertEqual(s.total(Allocation.objects.all(),'amount'),0)
        with self.assertRaises(ValidationError):s.reverse_payment(actor=self.actor,payment_id=p.pk,date=self.today,key=uuid4(),reason='Outra devolução')

    def test_sale_cancel_and_recovery_release_current_receipts_once(self):
        plan=self.plan();self.receipt(plan);self.payment('10')
        sales.cancel(actor=self.operator,sale_id=self.sale.pk,reason='Cancelamento')
        self.assertEqual(s.balance(self.payee),D('-10'))
        sales.cancel(actor=self.operator,sale_id=self.sale.pk,reason='Cancelamento novamente')
        self.assertEqual(Entry.objects.count(),2)
        self.sale.refresh_from_db()
        recover_sale(actor=self.actor,sale_id=self.sale.pk,revision=self.sale.revision,key=uuid4(),fees=self.sale.fees,reason='Cancelamento equivocado')
        self.assertEqual(s.balance(self.payee),D('12.50'))

    def test_adjustment_revalues_release_preserves_historical_terms(self):
        plan=self.plan();event=self.receipt(plan);self.payment('20');plan.refresh_from_db()
        s.adjust(actor=self.actor,plan_id=plan.pk,revision=plan.revision,rate=D('2'),override_total=None,key=uuid4(),reason='Percentual incorreto')
        self.assertEqual(s.balance(self.payee),D('-11'));self.sale.refresh_from_db();self.assertEqual(self.sale.commission,18)
        event.refresh_from_db();self.assertEqual(D(event.terms['rate']),5)
        self.assertEqual(s.total(Entry.objects.all(),'released'),9)

    def test_manual_total_override_and_reset(self):
        plan=self.plan();s.adjust(actor=self.actor,plan_id=plan.pk,revision=0,rate=D('5'),override_total=D('30'),key=uuid4(),reason='Acordo específico')
        plan.refresh_from_db();self.assertEqual(plan.total,30)
        s.adjust(actor=self.actor,plan_id=plan.pk,revision=plan.revision,rate=D('5'),override_total=None,key=uuid4(),reason='Retomar padrão')
        plan.refresh_from_db();self.assertEqual(plan.total,45)

    def test_schedule_revision_after_sale_correction_preserves_receipts_and_reconciles(self):
        plan=self.plan();self.receipt(plan);self.sale.refresh_from_db()
        values={f:getattr(self.sale,f) for f in FIELDS};values['discount']=D('200')
        correct_sale(actor=self.actor,sale_id=self.sale.pk,revision=self.sale.revision,key=uuid4(),reason='Desconto corrigido',values=values)
        plan.refresh_from_db();items=list(plan.installments.all())
        rows=[{'installment_id':i.pk,'due_date':i.due_date,'amount':amount} for i,amount in zip(items,[D('475'),D('375')])]
        s.revise_schedule(actor=self.actor,plan_id=plan.pk,revision=plan.revision,rows=rows,key=uuid4(),reason='Parcelas conciliadas com a venda')
        self.receipt(plan,'375',index=1)
        self.assertEqual(s.total(Entry.objects.all(),'released'),40)
        plan.refresh_from_db();rows[0]['amount']=D('474');rows[1]['amount']=D('376')
        with self.assertRaises(ValidationError):s.revise_schedule(actor=self.actor,plan_id=plan.pk,revision=plan.revision,rows=rows,key=uuid4(),reason='Valor menor que recebido')

    def test_sale_base_correction_recomputes_commission_without_stock(self):
        plan=self.plan();self.receipt(plan);self.sale.refresh_from_db();cmv=self.sale.cmv
        values={f:getattr(self.sale,f) for f in FIELDS};values['discount']=D('200')
        correct_sale(actor=self.actor,sale_id=self.sale.pk,revision=self.sale.revision,key=uuid4(),reason='Desconto corrigido',values=values)
        plan.refresh_from_db();self.sale.refresh_from_db()
        self.assertEqual(plan.base,800);self.assertEqual(self.sale.commission,40);self.assertEqual(self.sale.cmv,cmv)
        self.assertEqual(s.total(Entry.objects.all(),'released'),20)
        values['commission']=D('3')
        with self.assertRaises(ValidationError):correct_sale(actor=self.actor,sale_id=self.sale.pk,revision=self.sale.revision,key=uuid4(),reason='Outra',values=values)

    def test_monthly_carries_unpaid_and_separates_payment_date_from_accrual(self):
        from unittest.mock import patch
        # Synthetic clock: receipt month and payout month are deliberately different.
        plan=self.plan();self.receipt(plan)
        next_month=(self.today.replace(day=28)+timedelta(days=4)).replace(day=1)
        with patch('apps.commissions.services.timezone.localdate',return_value=next_month):self.payment('10',date=next_month)
        rows,events,start,end=q.monthly(self.actor,self.today)
        self.assertEqual(rows[0]['released'],D('22.50'));self.assertEqual(rows[0]['total'],D('22.50'));self.assertEqual(rows[0]['paid'],0)
        rows,events,start,end=q.monthly(self.actor,next_month)
        self.assertEqual(rows[0]['released'],0);self.assertEqual(rows[0]['paid'],10);self.assertEqual(rows[0]['previous'],D('12.50'))

    def test_employee_scope_get_and_post_denial(self):
        plan=self.plan();other=User.objects.create_user('other_commission')
        other.user_permissions.add(Permission.objects.get(codename='view_own_commissions'))
        self.client.force_login(other);self.assertEqual(self.client.get(reverse('commission_detail',args=[plan.pk])).status_code,404)
        self.assertNotContains(self.client.get(reverse('commissions')),'Cliente sintético')
        self.client.force_login(self.employee)
        self.assertContains(self.client.get(reverse('commission_detail',args=[plan.pk])),'Cliente sintético')
        for url in [reverse('commission_settings'),reverse('commission_new'),reverse('commission_payment_new'),reverse('commission_action',args=['adjust',plan.pk])]:
            self.assertEqual(self.client.post(url,{}).status_code,403)
        with self.assertRaises(PermissionDenied):s.adjust(actor=self.employee,plan_id=plan.pk,revision=0,rate=D('90'),override_total=None,key=uuid4(),reason='Inválido')

    def test_manager_independent_permission_does_not_need_sale_or_bank_access(self):
        manager=User.objects.create_user('commission_manager');manager.user_permissions.add(Permission.objects.get(codename='manage_commissions'))
        plan=self.plan(actor=manager);self.assertEqual(plan.total,45)
        self.assertFalse(manager.has_perm('core.view_finance'));self.assertFalse(manager.has_perm('core.view_costs'))

    def test_all_pages_render_and_filters(self):
        plan=self.plan();self.receipt(plan);self.payment('10');self.client.force_login(self.actor)
        for name,args in [('commissions',[]),('commission_review',[]),('commission_monthly',[]),('commission_payments',[]),('commission_settings',[]),('commission_detail',[plan.pk]),('commission_new',[])]:
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,200,name)
        self.assertContains(self.client.get(reverse('commission_review'),{'payment':'PENDING','receipt':'PARTIAL'}),'Cliente sintético')
        self.assertNotContains(self.client.get(reverse('commission_review'),{'payment':'UNPAID'}),'Cliente sintético')

    @skipUnless(connection.vendor=='postgresql','PostgreSQL ledger protection')
    def test_ledger_immutable_at_database(self):
        plan=self.plan();event=self.receipt(plan);payment=self.payment('1')
        for model,pk,field,value in [(Entry,event.pk,'released',D('999')),(Payment,payment.pk,'amount',D('999')),(Allocation,Allocation.objects.get().pk,'amount',D('999')),(Command,event.command_id,'reason','edited')]:
            with self.assertRaises(DatabaseError),transaction.atomic():model.objects.filter(pk=pk).update(**{field:value})

from django.test import TransactionTestCase
from django.db import close_old_connections
from concurrent.futures import ThreadPoolExecutor

@skipUnless(connection.vendor=='postgresql','PostgreSQL concurrent settlement')
class CommissionConcurrency(Fixture,TransactionTestCase):
    def test_two_distinct_payments_cannot_spend_same_release(self):
        plan=self.plan();self.receipt(plan)
        def worker(_):
            close_old_connections()
            try:
                actor=User.objects.get(pk=self.actor.pk)
                s.pay(actor=actor,payee_id=self.payee.pk,amount=D('22.50'),date=self.today,period=self.today,method='PIX',key=uuid4(),reason='Pagamento concorrente')
                return 'paid'
            except ValidationError:return 'blocked'
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
        self.assertCountEqual(results,['paid','blocked'])
        self.assertEqual(Payment.objects.count(),1);self.assertEqual(s.balance(self.payee),0)
