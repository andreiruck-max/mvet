from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal as D
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth.models import User, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, connections, close_old_connections, transaction, DatabaseError
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.core.models import Company
from apps.finance.models import FinancialAccount, FinancialTitle, FinancialEntry
from apps.finance import services as finance
from apps.purchases.models import Supplier
from .models import ChartOfAccount as Category, ClassificationRule as Rule, Expense, ExpenseRevision
from . import services as s, selectors


class Fixture:
    def setUp(self):
        self.today=timezone.localdate();self.cutoff=self.today-timedelta(days=10)
        Company.objects.create(pk=1,cutover_date=self.cutoff)
        self.admin=User.objects.create_superuser('expenses-owner')
        self.operator=User.objects.create_user('expenses-operator')
        self.operator.user_permissions.add(Permission.objects.get(codename='operate_expenses'))
        self.seller=User.objects.create_user('seller')
        self.seller.user_permissions.add(Permission.objects.get(codename='operate_sales'))
        self.root=s.save_category(actor=self.admin,data=dict(code='04',name='Despesas operacionais',nature='OPERATING',postable=False,active=True))
        self.category=s.save_category(actor=self.admin,data=dict(code='04.01',name='Contabilidade',nature='OPERATING',parent=self.root,postable=True,active=True))
        self.other=s.save_category(actor=self.admin,data=dict(code='04.02',name='Sistemas',nature='OPERATING',parent=self.root,postable=True,active=True))
        self.account=finance.save_account(actor=self.admin,data=dict(name='Banco teste',kind='BANK',opening_date=self.cutoff,opening_balance=D('1000')))

    def data(self,**changes):
        values=dict(document_date=self.today,competence=self.today,description='Contabilidade mensal',supplier=None,counterparty='Escritório',amount=D('100'),category=None,cost_center='',notes='',due_date=self.today+timedelta(days=10),account=self.account,recurrence_enabled=False)
        values.update(changes);return values

    def expense(self,**changes):return s.create_expense(actor=self.operator,key=uuid4(),data=self.data(**changes))

    def rule(self,**changes):
        values=dict(name='Contabilidade',priority=10,field='description',operator='CONTAINS',value='CONTABILIDADE',category=self.category,active=True)
        values.update(changes);return s.save_rule(actor=self.admin,data=values)

    def pay(self,expense):
        title=expense.title
        return finance.settle(actor=self.admin,key=uuid4(),title_id=title.pk,account_id=self.account.pk,date=self.today,principal=title.remaining,interest=D('0'),discount=D('0'),actual=title.remaining,revision=title.revision)


class ExpenseTests(Fixture,TestCase):
    def test_expense_accrual_is_separate_from_payment(self):
        obj=self.expense(category=self.category)
        self.assertEqual(FinancialTitle.objects.count(),1);self.assertFalse(FinancialEntry.objects.exists())
        groups,totals=selectors.expense_report({'start':self.today,'end':self.today})
        self.assertEqual(totals['OPERATING'],100)
        self.pay(obj)
        self.assertEqual(selectors.expense_report({'start':self.today,'end':self.today})[1]['OPERATING'],100)
        self.assertEqual(FinancialEntry.objects.get().amount,-100)

    def test_future_competence_can_be_prepaid(self):
        obj=self.expense(category=self.category,competence=self.today+timedelta(days=30))
        self.pay(obj)
        self.assertEqual(selectors.expense_report({'start':self.today,'end':self.today})[1]['OPERATING'],0)
        obj.title.refresh_from_db();self.assertEqual(obj.title.remaining,0)

    def test_duplicate_key_normalizes_money(self):
        key=uuid4();obj=s.create_expense(actor=self.operator,key=key,data=self.data(amount=D('100')))
        again=s.create_expense(actor=self.operator,key=key,data=self.data(amount=D('100.00')))
        self.assertEqual(obj.pk,again.pk);self.assertEqual(FinancialTitle.objects.count(),1)
        with self.assertRaises(ValidationError):s.create_expense(actor=self.operator,key=key,data=self.data(amount=D('101')))

    def test_manual_classification_overrides_rule(self):
        self.rule();obj=self.expense(category=self.other)
        self.assertEqual(obj.category,self.other);self.assertEqual(obj.classification,'MANUAL')

    def test_rule_case_insensitive_priority_and_stable_tie(self):
        first=self.rule(priority=5,category=self.other)
        self.rule(priority=5);obj=self.expense(description='CONTABILIDADE mensal')
        self.assertEqual(obj.category,self.other);self.assertEqual(obj.rule_snapshot['id'],first.pk)

    def test_supplier_document_and_counterparty_rules(self):
        supplier=Supplier.objects.create(legal_name='Escritório',document='12345678000190')
        self.rule(field='supplier_document',operator='EQUALS',value=supplier.document)
        self.assertEqual(self.expense(description='Serviço',supplier=supplier).category,self.category)
        self.rule(field='counterparty',operator='STARTS',value='agência',priority=1,category=self.other)
        self.assertEqual(self.expense(description='Serviço',counterparty='AGÊNCIA ABC').category,self.other)

    def test_unmatched_expense_is_visibly_unclassified(self):
        self.rule(value='Outro')
        obj=self.expense();self.assertIsNone(obj.category)
        self.assertEqual(selectors.expense_report({})[1]['NONE'],100)
        self.assertEqual(selectors.expenses({'status':'unclassified'}).count(),1)

    def test_inactive_rule_or_ancestor_is_ignored(self):
        self.rule();s.save_category(actor=self.admin,pk=self.root.pk,data={'active':False})
        obj=self.expense();self.assertIsNone(obj.category)
        with self.assertRaises(ValidationError):self.expense(category=self.category)

    def test_changing_rule_or_name_does_not_rewrite_history(self):
        rule=self.rule();obj=self.expense()
        s.save_rule(actor=self.admin,pk=rule.pk,data={'category':self.other})
        s.save_category(actor=self.admin,pk=self.category.pk,data={'name':'Novo nome'})
        obj.refresh_from_db();self.assertEqual(obj.category_snapshot['path'][-1]['name'],'Contabilidade')
        self.assertEqual(obj.rule_snapshot['id'],rule.pk)
        self.assertEqual(self.expense().category,self.other)

    def test_manual_reclassification_preserves_revision_and_cash(self):
        obj=self.expense();self.pay(obj)
        s.reclassify(actor=self.operator,pk=obj.pk,category=self.category,cost_center='Loja',reason='Conferência',revision=0)
        obj.refresh_from_db();self.assertEqual(obj.category,self.category);self.assertEqual(ExpenseRevision.objects.count(),1)
        self.assertEqual(obj.title.settled,100);self.assertEqual(FinancialEntry.objects.count(),1)

    def test_reclassification_requires_reason_and_current_revision(self):
        obj=self.expense()
        for reason,revision in [('',0),('Motivo',99)]:
            with self.assertRaises(ValidationError):s.reclassify(actor=self.operator,pk=obj.pk,category=self.category,cost_center='',reason=reason,revision=revision)

    def test_explicit_reapply_rules_is_audited(self):
        obj=self.expense(category=self.other);self.rule()
        s.reclassify(actor=self.operator,pk=obj.pk,category=None,cost_center='',reason='Aplicar regra conferida',revision=0,automatic=True)
        obj.refresh_from_db();self.assertEqual(obj.classification,'RULE');self.assertEqual(obj.category,self.category)

    def test_assets_and_group_categories_rejected(self):
        asset=s.save_category(actor=self.admin,data=dict(code='01',name='Estoque',nature='ASSET',postable=True,active=True))
        for cat in [asset,self.root]:
            with self.assertRaises(ValidationError):self.expense(category=cat)

    def test_financial_expenses_are_separate(self):
        cat=s.save_category(actor=self.admin,data=dict(code='05',name='Juros',nature='FINANCIAL',postable=True,active=True))
        self.expense(category=cat)
        totals=selectors.expense_report({})[1];self.assertEqual(totals['FINANCIAL'],100);self.assertEqual(totals['OPERATING'],0)

    def test_hierarchy_code_parent_and_cycles_rejected(self):
        for values in [dict(code='04.03',name='Inválida',nature='FINANCIAL',parent=self.root),dict(code='04.01.01',name='Filha de analítica',nature='OPERATING',parent=self.category),dict(code='04.05',name='Sem superior',nature='OPERATING'),dict(code='ABC',name='Código',nature='OPERATING')]:
            with self.assertRaises(ValidationError):s.save_category(actor=self.admin,data=values)
        with self.assertRaises(ValidationError):s.save_category(actor=self.admin,pk=self.root.pk,data={'parent':self.root})

    def test_used_category_structure_frozen_but_can_inactivate(self):
        self.expense(category=self.category)
        with self.assertRaises(ValidationError):s.save_category(actor=self.admin,pk=self.category.pk,data={'code':'04.09'})
        s.save_category(actor=self.admin,pk=self.category.pk,data={'active':False})
        self.assertEqual(selectors.expense_report({})[1]['OPERATING'],100)

    def test_cancel_requires_financial_reversal(self):
        obj=self.expense(category=self.category);op=self.pay(obj)
        with self.assertRaises(ValidationError):s.cancel_expense(actor=self.operator,pk=obj.pk,reason='Cancelar')
        finance.reverse(actor=self.admin,pk=op.pk,date=self.today,reason='Corrigir')
        s.cancel_expense(actor=self.operator,pk=obj.pk,reason='Cancelar')
        obj.refresh_from_db();self.assertEqual(obj.status,'CANCELLED');self.assertEqual(obj.title.status,'CANCELLED')
        self.assertEqual(selectors.expense_report({})[1]['OPERATING'],0)

    def test_finance_cannot_cancel_expense_title_directly(self):
        obj=self.expense()
        with self.assertRaises(ValidationError):finance.cancel_title(actor=self.admin,pk=obj.title_id,reason='Cancelar')

    def test_invalid_amount_dates_and_supplier_rollback(self):
        for values in [dict(amount=1.2),dict(amount=D('-1')),dict(amount=D('0')),dict(amount=D('1.001')),dict(competence=self.cutoff-timedelta(days=1)),dict(due_date=self.today-timedelta(days=1))]:
            with self.assertRaises(ValidationError):self.expense(**values)
        inactive=Supplier.objects.create(legal_name='Inativo',active=False)
        with self.assertRaises(ValidationError):self.expense(supplier=inactive)
        self.assertFalse(FinancialTitle.objects.exists())

    def test_audit_failure_rolls_back_title_and_expense(self):
        with patch('apps.expenses.services.audit',side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):self.expense()
        self.assertFalse(Expense.objects.exists());self.assertFalse(FinancialTitle.objects.exists())

    def test_recurrence_preview_month_end_and_idempotency(self):
        future=date(self.today.year+1,1,31)
        obj=self.expense(competence=future,due_date=future,category=self.category,recurrence_enabled=True)
        rows,token=s.recurrence_preview(obj,2)
        self.assertEqual(rows[0]['data']['competence'].month,2);self.assertEqual(rows[1]['data']['competence'].day,31)
        self.assertEqual(Expense.objects.count(),1)
        generated=s.generate_recurrence(actor=self.operator,pk=obj.pk,months=2,preview_hash=token)
        self.assertEqual(len(generated),2)
        self.assertEqual(s.generate_recurrence(actor=self.operator,pk=obj.pk,months=2,preview_hash=token),[])
        self.assertEqual(FinancialTitle.objects.count(),3);self.assertFalse(FinancialEntry.objects.exists())

    def test_recurrence_changed_rule_rejects_stale_preview(self):
        rule=self.rule();obj=self.expense(recurrence_enabled=True)
        _,token=s.recurrence_preview(obj,2)
        s.save_rule(actor=self.admin,pk=rule.pk,data={'category':self.other})
        with self.assertRaises(ValidationError):s.generate_recurrence(actor=self.operator,pk=obj.pk,months=2,preview_hash=token)
        self.assertEqual(Expense.objects.count(),1)

    def test_recurrence_stop_and_cancelled_month_not_regenerated(self):
        obj=self.expense(recurrence_enabled=True);_,token=s.recurrence_preview(obj,1)
        child=s.generate_recurrence(actor=self.operator,pk=obj.pk,months=1,preview_hash=token)[0]
        s.cancel_expense(actor=self.operator,pk=child.pk,reason='Cancelar mês')
        self.assertEqual(s.generate_recurrence(actor=self.operator,pk=obj.pk,months=1,preview_hash=token),[])
        s.stop_recurrence(actor=self.operator,pk=obj.pk)
        with self.assertRaises(ValidationError):s.generate_recurrence(actor=self.operator,pk=obj.pk,months=1,preview_hash=token)
        self.assertEqual(Expense.objects.count(),2)

    def test_report_parent_filter_counts_children_once(self):
        self.expense(category=self.category);self.expense(category=self.other,amount=D('50'))
        self.assertEqual(selectors.expense_report({'category':self.root})[1]['OPERATING'],150)

    def test_operator_cannot_access_reports_cash_or_configuration(self):
        obj=self.expense();self.client.force_login(self.operator)
        for name in ['expense_report','expense_report_api','finance','expense_configuration']:
            self.assertEqual(self.client.get(reverse(name)).status_code,403)
        self.assertEqual(self.client.get(reverse('expense_detail',args=[obj.pk])).status_code,200)
        with self.assertRaises(PermissionDenied):self.pay_as_operator(obj)

    def pay_as_operator(self,obj):
        finance.settle(actor=self.operator,key=uuid4(),title_id=obj.title_id,account_id=self.account.pk,date=self.today,principal=D('100'),interest=D('0'),discount=D('0'),actual=D('100'),revision=0)

    def test_seller_denied_urls_services_and_api(self):
        self.client.force_login(self.seller)
        for name in ['expenses','expense_new','expense_report_api','expense_configuration']:
            self.assertEqual(self.client.get(reverse(name)).status_code,403)
        with self.assertRaises(PermissionDenied):s.create_expense(actor=self.seller,key=uuid4(),data=self.data())

    def test_pages_csrf_and_post_only(self):
        obj=self.expense(recurrence_enabled=True);self.client.force_login(self.admin)
        for name,args in [('expenses',[]),('expense_new',[]),('expense_detail',[obj.pk]),('expense_report',[]),('expense_configuration',[]),('expense_category_new',[]),('expense_rule_new',[]),('expense_recurrence',[obj.pk])]:
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,200)
        self.assertEqual(self.client.get(reverse('expense_cancel',args=[obj.pk])).status_code,405)
        c=Client(enforce_csrf_checks=True);c.force_login(self.admin)
        self.assertEqual(c.post(reverse('expense_cancel',args=[obj.pk]),{'reason':'Test'}).status_code,403)
        self.assertEqual(self.client.get(reverse('expense_report_api')).status_code,200)


@skipUnless(connection.vendor=='postgresql','PostgreSQL required')
class PostgreSQLExpenses(Fixture,TransactionTestCase):
    def test_concurrent_expense_creation_idempotent(self):
        key=uuid4();data=self.data()
        def worker(_):
            close_old_connections()
            try:return s.create_expense(actor=User.objects.get(pk=self.operator.pk),key=key,data=data).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(worker,[1,2]))
        self.assertEqual(result[0],result[1]);self.assertEqual(FinancialTitle.objects.count(),1)

    def test_database_protects_accrual_and_requires_classification_revision(self):
        obj=self.expense()
        for mutate in [lambda:Expense.objects.filter(pk=obj.pk).update(amount=1),lambda:Expense.objects.filter(pk=obj.pk).update(competence=self.cutoff),lambda:Expense.objects.filter(pk=obj.pk).update(category=self.category),lambda:Expense.objects.filter(pk=obj.pk).delete()]:
            with self.assertRaises(DatabaseError),transaction.atomic():mutate()
        s.reclassify(actor=self.operator,pk=obj.pk,category=self.category,cost_center='',reason='Correção',revision=0)
        with self.assertRaises(DatabaseError),transaction.atomic():ExpenseRevision.objects.update(reason='Apagar evidência')
        s.cancel_expense(actor=self.operator,pk=obj.pk,reason='Cancelamento legítimo')
