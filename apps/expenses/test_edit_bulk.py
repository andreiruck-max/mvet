from datetime import timedelta
from decimal import Decimal as D
from uuid import uuid4
from unittest import skipUnless
from unittest.mock import patch
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import connection,transaction,DatabaseError
from django.test import TestCase,Client
from django.urls import reverse
from apps.finance.models import FinancialTitle,FinancialEntry,FinancialOperation
from apps.finance import services as finance
from .models import Expense,ExpenseRevision
from .tests import Fixture
from . import editing,bulk,selectors,services


class EditAndBulkTests(Fixture,TestCase):
    def edit(self,obj,**changes):
        obj.refresh_from_db()
        data=self.data(category=self.other,description='Descrição corrigida',amount=D('125.50'))
        data.update(changes)
        return editing.edit_expense(actor=self.admin,pk=obj.pk,revision=obj.revision,
            title_revision=obj.title.revision if obj.title_id else None,reason='Correção conferida',data=data)

    def test_edit_syncs_title_history_report_and_preserves_payments(self):
        obj=self.expense(category=self.category);op=self.pay(obj)
        obj=self.edit(obj,competence=self.today+timedelta(days=1),due_date=self.today+timedelta(days=20),counterparty='Outro favorecido',cost_center='Loja',notes='Detalhe')
        self.assertEqual(obj.amount,D('125.50'));self.assertEqual(obj.title.amount,obj.amount)
        self.assertEqual(obj.title.remaining,D('25.50'));self.assertEqual(obj.title.description,obj.description)
        self.assertEqual(obj.title.counterparty,'Outro favorecido');self.assertEqual(obj.category,self.other)
        self.assertEqual(FinancialEntry.objects.get().amount,D('-100'));op.refresh_from_db();self.assertEqual(op.principal,100)
        entry=obj.revisions.get();self.assertEqual(entry.before['expense']['amount'],'100.00')
        self.assertEqual(entry.after['expense']['amount'],'125.50');self.assertEqual(selectors.expense_report({})[1]['OPERATING'],D('125.50'))
        with self.assertRaises(ValidationError):self.edit(obj,amount=D('99'))
        with self.assertRaises(ValidationError):self.edit(obj,document_date=self.today+timedelta(days=1))
        self.client.force_login(self.admin)
        response=self.client.get(reverse('expense_detail',args=[obj.pk]));self.assertContains(response,'Descrição corrigida');self.assertContains(response,'125,50')

    def test_edit_stale_permissions_dates_rollback_and_noncash(self):
        obj=self.expense(category=self.category)
        self.edit(obj)
        with self.assertRaises(ValidationError):editing.edit_expense(actor=self.admin,pk=obj.pk,revision=0,title_revision=0,reason='Correção',data=self.data())
        with self.assertRaises(PermissionDenied):editing.edit_expense(actor=self.operator,pk=obj.pk,revision=1,title_revision=1,reason='Correção',data=self.data())
        with self.assertRaises(ValidationError):self.edit(obj,competence=self.cutoff-timedelta(days=1))
        with patch('apps.expenses.editing.audit',side_effect=RuntimeError),self.assertRaises(RuntimeError):self.edit(obj,amount=D('800'))
        obj.refresh_from_db();self.assertEqual(obj.amount,D('125.50'));self.assertEqual(obj.title.amount,D('125.50'));self.assertEqual(obj.revisions.count(),1)
        category=services.save_category(actor=self.admin,data=dict(code='08',name='Depreciação',nature='DEPRECIATION'))
        noncash=self.expense(category=category)
        self.edit(noncash,category=category,amount=D('50'))
        noncash.refresh_from_db();self.assertIsNone(noncash.title_id);self.assertEqual(noncash.amount,50)
        with self.assertRaises(ValidationError):self.edit(obj,category=category)

    def test_form_edit_and_post_csrf(self):
        obj=self.expense(category=self.category)
        self.client.force_login(self.admin)
        response=self.client.get(reverse('expense_edit',args=[obj.pk]));self.assertEqual(response.status_code,200)
        data=self.data(description='Editada pela tela',category=self.other.pk,supplier='',account=self.account.pk,amount='130',reason='Conferência',revision=0,title_revision=0)
        response=self.client.post(reverse('expense_edit',args=[obj.pk]),data)
        self.assertEqual(response.status_code,302,response.context and response.context['form'].errors)
        obj.refresh_from_db();self.assertEqual(obj.description,'Editada pela tela');self.assertEqual(obj.amount,130)
        self.client.force_login(self.operator);self.assertEqual(self.client.get(reverse('expense_edit',args=[obj.pk])).status_code,403)
        client=Client(enforce_csrf_checks=True);client.force_login(self.admin)
        self.assertEqual(client.post(reverse('expense_edit',args=[obj.pk]),data).status_code,403)

    def test_bulk_distinct_categories_partial_future_retry_and_atomic_failure(self):
        a=self.expense(category=self.category);b=self.expense(category=self.other,amount=D('200'))
        finance.settle(actor=self.admin,key=uuid4(),title_id=a.title_id,account_id=self.account.pk,date=self.today,
            principal=D('40'),interest=D(0),discount=D(0),actual=D('40'),revision=0)
        rows=bulk.preview_rows(bulk.selection([a.pk,b.pk]));key=uuid4()
        # Real second-row conflict must undo the first settlement.
        finance.schedule_title(actor=self.admin,pk=b.title_id,due_date=b.title.due_date,account=self.account,notes='Alteração concorrente',revision=0)
        with self.assertRaises(ValidationError):bulk.settle_batch(actor=self.admin,key=key,rows=rows,account_id=self.account.pk,date=self.today)
        a.title.refresh_from_db();self.assertEqual(a.title.settled,40);self.assertEqual(FinancialOperation.objects.count(),1)
        rows=bulk.preview_rows(bulk.selection([a.pk,b.pk]));future=self.today+timedelta(days=1)
        operations=bulk.settle_batch(actor=self.admin,key=key,rows=rows,account_id=self.account.pk,date=future)
        self.assertEqual(sum(op.principal for op in operations),260)
        repeated=bulk.settle_batch(actor=self.admin,key=key,rows=rows,account_id=self.account.pk,date=future)
        self.assertEqual([op.pk for op in operations],[op.pk for op in repeated]);self.assertEqual(FinancialOperation.objects.count(),3)
        a.refresh_from_db();b.refresh_from_db();self.assertEqual(a.category,self.category);self.assertEqual(b.category,self.other)
        self.assertEqual(FinancialEntry.objects.filter(operation__in=operations).count(),2)
        self.assertEqual(a.title.remaining,0);self.assertEqual(b.title.remaining,0)

    def test_bulk_preview_signed_permissions_and_edit_conflict(self):
        a=self.expense(category=self.category);b=self.expense(category=self.other)
        url=reverse('expense_bulk_payment');self.client.force_login(self.admin)
        review=self.client.post(url,{'expense_ids':[a.pk,b.pk],'action':'review','account':self.account.pk,'date':str(self.today)})
        self.assertContains(review,'Confirmar baixa de 2 despesas');self.assertFalse(FinancialEntry.objects.exists())
        token=review.context['preview'];self.assertTrue(token)
        self.assertEqual(self.client.post(url,{'action':'confirm','preview':token+'invalid'}).status_code,400)
        self.edit(b)
        self.assertEqual(self.client.post(url,{'action':'confirm','preview':token}).status_code,400)
        self.assertFalse(FinancialEntry.objects.exists())
        review=self.client.post(url,{'expense_ids':[a.pk,b.pk],'action':'review','account':self.account.pk,'date':str(self.today)})
        token=review.context['preview']
        self.assertEqual(self.client.post(url,{'action':'confirm','preview':token}).status_code,302)
        self.assertEqual(self.client.post(url,{'action':'confirm','preview':token}).status_code,302)
        self.assertEqual(FinancialEntry.objects.count(),2)
        self.assertEqual(self.client.post(url,{'expense_ids':[a.pk,a.pk]}).status_code,400)
        self.client.force_login(self.operator);self.assertEqual(self.client.post(url,{'expense_ids':[a.pk]}).status_code,403)
        self.assertEqual(self.client.get(url).status_code,405)
        with self.assertRaises(PermissionDenied):bulk.settle_batch(actor=self.operator,key=uuid4(),rows=[],account_id=self.account.pk,date=self.today)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL guards')
    def test_sql_protection_with_and_without_revision_context(self):
        obj=self.expense(category=self.category);self.edit(obj)
        for model,pk,values in [(Expense,obj.pk,{'amount':900}),(FinancialTitle,obj.title_id,{'amount':900}),
                                (ExpenseRevision,obj.revisions.get().pk,{'reason':'Apagar histórico'})]:
            with self.assertRaises(DatabaseError),transaction.atomic():model.objects.filter(pk=pk).update(**values)
        with self.assertRaises(DatabaseError),transaction.atomic():
            with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.expense_edit','99999999',true)")
            Expense.objects.filter(pk=obj.pk).update(amount=900)
