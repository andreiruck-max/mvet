from datetime import timedelta
from decimal import Decimal
from django.db import connection, transaction, IntegrityError, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone
from apps.core.models import Company
from .tests import Fixture
from .models import SalesChannel, TaxRule, TaxRateChange, SaleTaxRevision, Sale
from .taxes import change_rate


class ConfigurationCompanyMigrationTests(Fixture, TransactionTestCase):
    def test_tax_revision_and_sale_snapshots_survive(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        sale = self.confirmed(date=yesterday)
        change_rate(actor=self.actor, rule_id=self.rule.pk, rate=Decimal('8'),
                    effective_from=yesterday, base='REVENUE', reason='Teste sintético', revision=0)
        sale_before = Sale.objects.values().get(pk=sale.pk)
        models = [SalesChannel, TaxRule, TaxRateChange, SaleTaxRevision]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('sales', '0018_sale_company_identity')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            originals = {}
            for current in models:
                model = state.get_model('sales', current.__name__)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[current.__name__] = (fields, list(model.objects.order_by('pk').values(*fields)))
            MigrationExecutor(connection).migrate(latest)
            for model in models:
                fields, rows = originals[model.__name__]
                self.assertTrue(rows)
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertEqual(set(model.objects.values_list('company_id', flat=True)), {1})
            self.assertEqual(Sale.objects.values().get(pk=sale.pk), sale_before)
            Company.objects.get_or_create(pk=2, defaults={'active': False})
            for model in [SalesChannel, TaxRule]:
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.update(company_id=2)
            with self.assertRaises(DatabaseError), transaction.atomic():
                SaleTaxRevision.objects.update(after_amount=999)
        finally:
            MigrationExecutor(connection).migrate(latest)
