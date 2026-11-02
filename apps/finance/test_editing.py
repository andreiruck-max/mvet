from decimal import Decimal as D
from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase
from django.urls import reverse
from .tests import Fixture
from . import editing, selectors
from .models import FinancialTitle as Title, FinancialEntry, FinancialTitleRevision


class TitleEditingTests(Fixture,TestCase):
    def data(self,title,**changes):
        data={key:getattr(title,key) for key in editing.FIELDS if key not in ['revision','account_id']}
        data['account']=title.account;data.update(changes);return data

    def edit(self,title,**changes):
        return editing.edit_title(actor=self.admin,pk=title.pk,revision=title.revision,reason='Correção conferida',data=self.data(title,**changes))

    def test_all_fields_and_accrual_without_cash(self):
        from apps.reporting.selectors import financial_result
        title=self.title()
        changed=self.edit(title,description='Rendimento corrigido',amount=D(150),counterparty='Cliente',category='FINANCIAL',direction='RECEIVE',date=self.today,due_date=self.today+timedelta(days=4),account=self.b,notes='Detalhe')
        self.assertEqual(changed.amount,150);self.assertEqual(changed.account,self.b)
        self.assertEqual(changed.edits.get().before['amount'],'100.00')
        self.assertEqual(changed.edits.get().after['amount'],'150.00')
        self.assertEqual(FinancialEntry.objects.count(),0)
        self.assertEqual(financial_result(dict(start=self.today,end=self.today))['income'],150)
        self.assertEqual(changed.counterparty,'Cliente')
        with self.assertRaises(ValidationError):self.edit(title,description='Versão antiga')
        self.assertEqual(changed.edits.count(),1)

    def test_paid_partial_future_and_protected_ledger(self):
        title=self.title()
        self.settle(title,principal=D(40),actual=D(40),date=self.today+timedelta(days=2))
        title.refresh_from_db()
        ledger=list(FinancialEntry.objects.values())
        with self.assertRaises(ValidationError):self.edit(title,amount=D(39))
        with self.assertRaises(ValidationError):self.edit(title,direction='RECEIVE')
        with self.assertRaises(ValidationError):self.edit(title,date=self.today+timedelta(days=3),due_date=self.today+timedelta(days=4))
        changed=self.edit(title,amount=D(40),description='Nome corrigido',category='FINANCIAL')
        self.assertEqual(changed.remaining,0)
        changed=self.edit(changed,amount=D(50),account=self.b)
        self.assertEqual(changed.remaining,10)
        self.assertEqual(list(FinancialEntry.objects.values()),ledger)
        self.assertEqual(changed.settled,40)

    def test_purchase_current_obligation_and_original_document(self):
        from apps.purchases.selectors import supplier_report
        purchase=self.purchase()
        title=Title.objects.get(purchase_installment__purchase=purchase)
        changed=self.edit(title,amount=D(120),counterparty='',description='Parcela renegociada')
        installment=purchase.installments.get()
        self.assertEqual(installment.amount,100)
        self.assertEqual(installment.effective_amount,120)
        self.assertEqual(installment.remaining,120)
        self.assertEqual(changed.counterparty,'Fornecedor')
        self.assertEqual(supplier_report(purchase.supplier)[0]['outstanding'],120)
        purchase.refresh_from_db();self.assertEqual(purchase.total,100)
        with self.assertRaises(ValidationError):self.edit(changed,direction='RECEIVE')

    def test_permissions_opening_http_and_database_guards(self):
        title=self.title()
        with self.assertRaises(PermissionDenied):editing.edit_title(actor=self.operator,pk=title.pk,revision=title.revision,reason='Teste',data=self.data(title))
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('financial_title_edit',args=[title.pk])).status_code,403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('financial_titles')),'Editar')
        data=self.data(title,description='Editado pela tela');data['account']=self.a.pk
        data.update(revision=title.revision,reason='Conferência')
        response=self.client.post(reverse('financial_title_edit',args=[title.pk]),data)
        self.assertEqual(response.status_code,302)
        self.assertContains(self.client.get(reverse('financial_title',args=[title.pk])),'Conferência')
        title.refresh_from_db()
        with self.assertRaises(DatabaseError),transaction.atomic():Title.objects.filter(pk=title.pk).update(amount=D(300))
        with self.assertRaises(DatabaseError),transaction.atomic():title.edits.update(reason='Apagar histórico')
        with self.assertRaises(DatabaseError),transaction.atomic():title.edits.all().delete()
        with self.assertRaises(ValidationError):self.edit(title,category='OPENING')
        changed=self.edit(title,opening=True,date=self.cutoff-timedelta(days=1))
        self.assertEqual(changed.category,'OPENING')
        self.assertEqual(FinancialTitleRevision.objects.count(),2)


class ExpenseEditingAccessTests(TestCase):
    def test_linked_title_redirects_to_expense_edit(self):
        from apps.reporting.tests import ReportingFixture
        fixture=ReportingFixture();fixture.setUp()
        expense=fixture.expense()
        self.client.force_login(fixture.actor)
        self.assertRedirects(self.client.get(reverse('financial_title_edit',args=[expense.title_id])),reverse('expense_edit',args=[expense.pk]))
        self.assertContains(self.client.get(reverse('expenses')),'Editar')
        self.assertContains(self.client.get(reverse('financial_title',args=[expense.title_id])),'Operacionais')
        with self.assertRaises(ValidationError):
            editing.edit_title(actor=fixture.actor,pk=expense.title_id,revision=0,reason='Teste',data={})
