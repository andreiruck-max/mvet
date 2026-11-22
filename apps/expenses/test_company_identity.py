from django.db import connection, transaction, DatabaseError, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from apps.core.models import Company
from apps.finance.models import FinancialTitle, FinancialEntry
from .tests import Fixture
from .models import Expense, ExpenseRevision


class ExpenseCompanyTests(Fixture, TestCase):
    def test_paid_expense_and_title_have_primary_owner(self):
        expense = self.expense(category=self.category)
        self.pay(expense)
        self.assertEqual(expense.company_id, 1)
        expense.title.refresh_from_db()
        self.assertEqual(expense.title.company_id, 1)
        self.assertEqual(expense.title.remaining, 0)
        self.assertEqual(FinancialEntry.objects.get().company_id, 1)

    def test_secondary_expense_is_rejected(self):
        Company.objects.get_or_create(pk=2, defaults={'active': False})
        with self.assertRaises(IntegrityError), transaction.atomic():
            Expense.objects.create(company_id=2, actor=self.admin, description='Forbidden',
                document_date=self.today, competence=self.today, amount=10,
                category_snapshot={'nature':'DEPRECIATION'})


class ExpenseCompanyMigrationTests(Fixture, TransactionTestCase):
    def test_paid_history_and_revision_survive(self):
        expense = self.expense(category=self.category)
        self.pay(expense)
        ExpenseRevision.objects.create(expense=expense, actor=self.admin, number=1,
            reason='Historical revision', before={'amount':'100'}, after={'amount':'100'})
        titles = list(FinancialTitle.objects.order_by('pk').values())
        entries = list(FinancialEntry.objects.order_by('pk').values())
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('expenses', '0006_audited_expense_edits')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            originals = {}
            for name in ['Expense','ExpenseRevision']:
                model = state.get_model('expenses', name)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields, list(model.objects.order_by('pk').values(*fields)))
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgrelid IN ('expenses_expense'::regclass,'expenses_expenserevision'::regclass) ORDER BY oid")
                triggers = cursor.fetchall()
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            after = executor.loader.project_state(latest).apps
            for name, (fields, rows) in originals.items():
                model = after.get_model('expenses', name)
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertEqual(set(model.objects.values_list('company_id',flat=True)), {1})
            self.assertEqual(list(FinancialTitle.objects.order_by('pk').values()), titles)
            self.assertEqual(list(FinancialEntry.objects.order_by('pk').values()), entries)
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid,tgname,tgenabled FROM pg_trigger WHERE tgrelid IN ('expenses_expense'::regclass,'expenses_expenserevision'::regclass) ORDER BY oid")
                self.assertTrue(set(triggers).issubset(set(cursor.fetchall())))
            with self.assertRaises(DatabaseError), transaction.atomic():
                Expense.objects.filter(pk=expense.pk).update(amount=999)
        finally:
            MigrationExecutor(connection).migrate(latest)
