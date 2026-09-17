from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal as D
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth.models import User, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, connections, close_old_connections, transaction, DatabaseError
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse as url
from django.utils import timezone
from apps.core.models import Company
from apps.inventory.models import StockLocation
from apps.products.models import Product
from apps.purchases.models import Supplier
from apps.purchases import services as purchases
from .models import FinancialAccount as Account, FinancialTitle as Title, FinancialOperation as Operation, FinancialEntry as Entry
from . import services as s, selectors


class Fixture:
    def setUp(self):
        self.today=timezone.localdate();self.cutoff=self.today-timedelta(days=10)
        Company.objects.create(pk=1,cutover_date=self.cutoff)
        self.admin=User.objects.create_superuser('fin-admin')
        self.operator=User.objects.create_user('fin-op')
        self.operator.user_permissions.add(Permission.objects.get(codename='operate_finance'))
        self.seller=User.objects.create_user('seller');self.seller.user_permissions.add(Permission.objects.get(codename='operate_sales'))
        self.a=s.save_account(actor=self.admin,data=dict(name='Banco A',kind='BANK',opening_date=self.cutoff,opening_balance=D('1000')))
        self.b=s.save_account(actor=self.admin,data=dict(name='Banco B',kind='BANK',opening_date=self.cutoff,opening_balance=D('0')))

    def title(self,**kwargs):
        data=dict(direction='PAY',description='Fornecedor',date=self.cutoff,due_date=self.today,amount=D('100'),account=self.a)
        data.update(kwargs)
        return s.create_title(actor=self.operator,key=uuid4(),data=data)

    def settle(self,title,**kwargs):
        title.refresh_from_db()
        data=dict(actor=self.operator,key=uuid4(),title_id=title.pk,account_id=self.a.pk,date=self.today,principal=title.remaining,interest=D('0'),discount=D('0'),actual=title.remaining,revision=title.revision)
        data.update(kwargs);return s.settle(**data)

    def purchase(self):
        location=StockLocation.objects.create(name='Mercadovet')
        product=Product.objects.create(sku='F01',name='Produto')
        supplier=Supplier.objects.create(legal_name='Fornecedor')
        p=purchases.save_draft(actor=self.admin,key=uuid4(),data=dict(supplier=supplier,document='F01',series='',date=self.today,location=location,discount=D('0'),freight=D('0'),other_costs=D('0'),notes=''),items=[(product.pk,D('2'),D('50'))],installments=[(self.today,D('100'),'')])
        return purchases.confirm(actor=self.admin,purchase_id=p.pk,revision=p.revision)


class FinanceTests(Fixture,TestCase):
    def test_obligation_does_not_move_cash(self):
        t=self.title();self.assertEqual(Entry.objects.count(),0)
        rows,_=selectors.daily_cash(self.today,self.today,self.a.pk)
        self.assertEqual(rows[0]['final'],1000);self.assertEqual(rows[0]['projected'],900)

    def test_payment_partial_full_and_no_projection_duplication(self):
        t=self.title();self.settle(t,principal=D('40'),actual=D('40'))
        t.refresh_from_db();self.assertEqual(t.remaining,60)
        rows,_=selectors.daily_cash(self.today,self.today,self.a.pk)
        self.assertEqual(rows[0]['final'],960);self.assertEqual(rows[0]['projected'],900)
        self.settle(t);t.refresh_from_db();self.assertEqual(t.display_status,'Pago')
        rows,_=selectors.daily_cash(self.today,self.today,self.a.pk);self.assertEqual(rows[0]['final'],rows[0]['projected'])

    def test_receipt_is_credit(self):
        self.settle(self.title(direction='RECEIVE'))
        self.assertEqual(Entry.objects.get().amount,100)

    def test_interest_discount_and_actual_difference(self):
        op=self.settle(self.title(),interest=D('10'),discount=D('3'),actual=D('107'),notes='Juros e desconto negociados')
        self.assertEqual(op.actual,107);self.assertEqual(Entry.objects.get().amount,-107)

    def test_unexplained_difference_rejected(self):
        t=self.title()
        for kw in [dict(actual=D('99')),dict(interest=D('1'),actual=D('101')),dict(principal=D('101'),actual=D('101'))]:
            with self.assertRaises(ValidationError):self.settle(t,**kw)
        self.assertFalse(Entry.objects.exists())

    def test_full_discount_records_settlement_without_bank_entry(self):
        t=self.title();self.settle(t,discount=D('100'),actual=D('0'),notes='Abatimento total')
        self.assertFalse(Entry.objects.exists());t.refresh_from_db();self.assertEqual(t.remaining,0)

    def test_key_replay_exact_and_changed(self):
        t=self.title();key=uuid4();op=self.settle(t,key=key)
        result=s.settle(actor=self.operator,key=key,title_id=t.pk,account_id=self.a.pk,date=self.today,principal=D('100'),interest=D('0'),discount=D('0'),actual=D('100'),revision=0)
        self.assertEqual(result.pk,op.pk)
        with self.assertRaises(ValidationError):self.settle(t,key=key)
        self.assertEqual(Entry.objects.count(),1)

    def test_stale_revision_blocks_double_click_with_new_uuid(self):
        t=self.title();self.settle(t,principal=D('40'),actual=D('40'))
        with self.assertRaises(ValidationError):self.settle(t,principal=D('40'),actual=D('40'),revision=0)

    def test_reverse_reopens_principal_without_deleting_history(self):
        t=self.title();op=self.settle(t);rev=s.reverse(actor=self.operator,pk=op.pk,date=self.today,reason='Correção')
        again=s.reverse(actor=self.operator,pk=op.pk,date=self.today,reason='Correção')
        self.assertEqual(rev.pk,again.pk);self.assertEqual(Entry.objects.count(),2)
        t.refresh_from_db();self.assertEqual(t.remaining,100)
        with self.assertRaises(ValidationError):s.reverse(actor=self.operator,pk=rev.pk,date=self.today,reason='Não')

    def test_payment_rollback_on_audit_failure(self):
        t=self.title()
        with patch('apps.finance.services.audit',side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):self.settle(t)
        t.refresh_from_db();self.assertEqual(t.settled,0);self.assertFalse(Entry.objects.exists())

    def test_future_realized_and_preopening_rejected(self):
        t=self.title()
        for date in [self.today+timedelta(days=1),self.cutoff-timedelta(days=1)]:
            with self.assertRaises(ValidationError):self.settle(t,date=date)
        with self.assertRaises(ValidationError):s.transfer(actor=self.operator,key=uuid4(),source_id=self.a.pk,destination_id=self.b.pk,date=self.today+timedelta(days=1),amount=D('1'))

    def test_negative_and_float_rejected(self):
        for amount in [D('-1'),D('0'),1.2,D('1.001')]:
            with self.assertRaises(ValidationError):self.title(amount=amount)

    def test_bank_transfer_conserves_total_and_reverse(self):
        op=s.transfer(actor=self.operator,key=uuid4(),source_id=self.a.pk,destination_id=self.b.pk,date=self.today,amount=D('300'))
        rows,_=selectors.daily_cash(self.today,self.today)
        self.assertEqual(sum(r['final'] for r in rows),1000)
        self.assertEqual([r['final'] for r in rows],[D('700'),D('300')])
        s.reverse(actor=self.operator,pk=op.pk,date=self.today,reason='Corrigir')
        self.assertEqual(sum(Entry.objects.values_list('amount',flat=True)),0)

    def test_same_account_transfer_rejected(self):
        with self.assertRaises(ValidationError):s.transfer(actor=self.operator,key=uuid4(),source_id=self.a.pk,destination_id=self.a.pk,date=self.today,amount=D('1'))

    def test_planned_transfer_then_post_no_duplicate(self):
        op=s.transfer(actor=self.operator,key=uuid4(),source_id=self.a.pk,destination_id=self.b.pk,date=self.today+timedelta(days=1),amount=D('100'),planned=True)
        rows,_=selectors.daily_cash(self.today,self.today+timedelta(days=1),self.a.pk)
        self.assertEqual(rows[-1]['final'],1000);self.assertEqual(rows[-1]['projected'],900)
        s.post_transfer(actor=self.operator,pk=op.pk,date=self.today);s.post_transfer(actor=self.operator,pk=op.pk,date=self.today)
        self.assertEqual(Entry.objects.count(),2)

    def test_cancel_planned_transfer_no_cash(self):
        op=s.transfer(actor=self.operator,key=uuid4(),source_id=self.a.pk,destination_id=self.b.pk,date=self.today,amount=D('100'),planned=True)
        s.reverse(actor=self.operator,pk=op.pk,date=self.today,reason='Desistência')
        rows,_=selectors.daily_cash(self.today,self.today,self.a.pk);self.assertEqual(rows[0]['projected'],1000)

    def test_past_entry_affects_later_balances(self):
        self.settle(self.title(),date=self.today-timedelta(days=2))
        rows,_=selectors.daily_cash(self.today,self.today+timedelta(days=2),self.a.pk)
        self.assertTrue(all(r['initial']==900 and r['final']==900 for r in rows))

    def test_overdue_rolls_to_today_and_unallocated_visible(self):
        self.title(due_date=self.today-timedelta(days=2));self.title(account=None,amount=D('30'))
        rows,unassigned=selectors.daily_cash(self.today,self.today,self.a.pk)
        self.assertEqual(rows[0]['projected'],900);self.assertEqual(unassigned['pay'],30)

    def test_schedule_account_and_due_date(self):
        t=self.title()
        s.schedule_title(actor=self.operator,pk=t.pk,due_date=self.today+timedelta(days=3),account=self.b,notes='Novo prazo',revision=0)
        t.refresh_from_db();self.assertEqual(t.account,self.b)
        with self.assertRaises(ValidationError):s.schedule_title(actor=self.operator,pk=t.pk,due_date=self.today,account=self.a,notes='',revision=0)

    def test_opening_legacy_and_negative_bank_balance(self):
        t=self.title(opening=True,date=self.cutoff-timedelta(days=100),due_date=self.cutoff-timedelta(days=10))
        self.assertEqual(t.category,'OPENING');self.settle(t)
        s.save_account(actor=self.admin,pk=self.b.pk,data={'opening_balance':D('-20')})
        rows,_=selectors.daily_cash(self.today,self.today,self.b.pk);self.assertEqual(rows[0]['final'],-20)

    def test_account_opening_after_report_start(self):
        s.save_account(actor=self.admin,pk=self.b.pk,data={'opening_date':self.today,'opening_balance':D('50')})
        rows,_=selectors.daily_cash(self.cutoff,self.today,self.b.pk)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['initial'],50)

    def test_used_account_no_delete_no_opening_edit(self):
        self.title()
        with self.assertRaises(ValidationError):s.delete_account(actor=self.admin,pk=self.a.pk)
        with self.assertRaises(ValidationError):s.save_account(actor=self.admin,pk=self.a.pk,data={'opening_balance':D('1')})
        s.save_account(actor=self.admin,pk=self.a.pk,data={'active':False})
        with self.assertRaises(ValidationError):self.settle(Title.objects.get())
        s.delete_account(actor=self.admin,pk=self.b.pk);self.assertFalse(Account.objects.filter(pk=self.b.pk).exists())

    def test_cancel_title_requires_reversal(self):
        t=self.title();op=self.settle(t)
        with self.assertRaises(ValidationError):s.cancel_title(actor=self.operator,pk=t.pk,reason='Cancelar')
        s.reverse(actor=self.operator,pk=op.pk,date=self.today,reason='Estorno')
        s.cancel_title(actor=self.operator,pk=t.pk,reason='Cancelar');t.refresh_from_db();self.assertEqual(t.status,'CANCELLED')

    def test_purchase_title_generated_and_paid_status(self):
        p=self.purchase();t=Title.objects.get(purchase_installment__purchase=p)
        self.assertEqual(t.amount,100);self.assertFalse(Entry.objects.exists())
        self.settle(t);self.assertEqual(p.installments.get().display_status,'Pago')
        with self.assertRaises(ValidationError):purchases.cancel(actor=self.admin,purchase_id=p.pk,reason='Cancelar')
        from apps.purchases.selectors import supplier_report
        summary,_,_=supplier_report(p.supplier);self.assertIsNone(summary['outstanding'])
        s.reverse(actor=self.operator,pk=Operation.objects.get(kind='SETTLEMENT').pk,date=self.today,reason='Estorno')
        purchases.cancel(actor=self.admin,purchase_id=p.pk,reason='Cancelar');t.refresh_from_db();self.assertEqual(t.status,'CANCELLED')

    def test_linked_title_cannot_cancel_directly(self):
        self.purchase();t=Title.objects.get()
        with self.assertRaises(ValidationError):s.cancel_title(actor=self.operator,pk=t.pk,reason='Cancelar')

    def test_sale_generates_receivable_and_blocks_cancel_after_receipt(self):
        from apps.sales import services as sales
        from apps.sales.models import SalesChannel, TaxRule
        p=self.purchase();purchases.receive(actor=self.admin,purchase_id=p.pk,date=self.today,revision=p.revision)
        product=p.items.get().product
        channel=SalesChannel.objects.create(name='Loja');rule=TaxRule.objects.create(name='Teste',rate=D('0'),starts_on=self.cutoff,base='REVENUE')
        data=dict(date=self.today,invoice_number='F100',invoice_series='',channel=channel,location=p.location,products_amount=D('100'),discount=D('0'),shipping_received=D('0'),shipping_paid=D('0'),fees=D('0'),difal=D('0'),commission=D('0'),other_costs=D('0'),tax_rule=rule,tax_override=None,tax_reason='',notes='')
        sale=sales.save_draft(actor=self.seller,key=uuid4(),data=data,items=[(product.pk,D('1'))])
        self.assertFalse(Title.objects.filter(sale=sale).exists())
        sale=sales.confirm(actor=self.seller,sale_id=sale.pk,revision=sale.revision)
        title=Title.objects.get(sale=sale);self.assertEqual(title.amount,100)
        op=self.settle(title)
        with self.assertRaises(ValidationError):sales.cancel(actor=self.seller,sale_id=sale.pk,reason='Cancelar')
        s.reverse(actor=self.operator,pk=op.pk,date=self.today,reason='Estorno')
        sales.cancel(actor=self.seller,sale_id=sale.pk,reason='Cancelar')
        title.refresh_from_db();self.assertEqual(title.status,'CANCELLED')

    def test_permissions_urls_api_and_services(self):
        t=self.title();self.client.force_login(self.seller)
        for name,args in [('finance',[]),('financial_titles',[]),('financial_title',[t.pk]),('cash_api',[]),('financial_accounts',[])]:
            self.assertEqual(self.client.get(url(name,args=args)).status_code,403)
        with self.assertRaises(PermissionDenied):s.transfer(actor=self.seller,key=uuid4(),source_id=self.a.pk,destination_id=self.b.pk,date=self.today,amount=D('10'))
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url('financial_titles')).status_code,200)
        self.assertEqual(self.client.get(url('finance')).status_code,403)
        self.assertEqual(self.client.get(url('financial_accounts')).status_code,403)

    def test_forms_pages_csrf_and_post_only(self):
        t=self.title();self.client.force_login(self.admin)
        for name,args in [('finance',[]),('financial_accounts',[]),('financial_title_new',[]),('financial_transfer',[]),('financial_title',[t.pk]),('financial_account_edit',[self.a.pk])]:
            self.assertEqual(self.client.get(url(name,args=args)).status_code,200)
        self.assertEqual(self.client.get(url('financial_settle',args=[t.pk])).status_code,405)
        c=Client(enforce_csrf_checks=True);c.force_login(self.admin)
        self.assertEqual(c.post(url('financial_settle',args=[t.pk]),{}).status_code,403)
        self.assertEqual(self.client.get(url('cash_api'),{'start':self.cutoff,'end':self.today}).status_code,200)
        self.assertEqual(self.client.get(url('cash_api'),{'start':self.cutoff,'end':self.today+timedelta(days=100)}).status_code,400)


@skipUnless(connection.vendor=='postgresql','PostgreSQL required')
class PostgreSQLFinance(Fixture,TransactionTestCase):
    def test_concurrent_double_click_is_idempotent(self):
        t=self.title();key=uuid4()
        def worker(_):
            close_old_connections()
            try:return s.settle(actor=User.objects.get(pk=self.operator.pk),key=key,title_id=t.pk,account_id=self.a.pk,date=self.today,principal=D('100'),interest=D('0'),discount=D('0'),actual=D('100'),revision=0).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(worker,[1,2]))
        self.assertEqual(result[0],result[1]);self.assertEqual(Entry.objects.count(),1)

    def test_database_rejects_ledger_changes_and_unbalanced_transfers(self):
        t=self.title();op=self.settle(t)
        for mutate in [lambda:Entry.objects.update(amount=1),lambda:Operation.objects.filter(pk=op.pk).update(actual=1),lambda:Title.objects.filter(pk=t.pk).update(settled=0),lambda:Title.objects.filter(pk=t.pk).update(amount=200),lambda:Account.objects.filter(pk=self.a.pk).update(opening_balance=1)]:
            with self.assertRaises(DatabaseError),transaction.atomic():mutate()
        with self.assertRaises(DatabaseError),transaction.atomic():
            Operation.objects.create(kind='TRANSFER',date=self.today,actual=10,actor=self.admin,fingerprint='test')
        s.reverse(actor=self.operator,pk=op.pk,date=self.today,reason='Legítimo')
