from decimal import Decimal
from uuid import uuid4
from django.db import connection, transaction, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from .tests import Fixture
from .models import Sale, SaleCorrection, SaleCostRevision, SaleRecovery
from .corrections import correct_sale, FIELDS
from .cost_corrections import correct_cost
from .services import cancel
from .recovery import recover_sale


class RevisionCompanyMigrationTests(Fixture, TransactionTestCase):
    def test_correction_cost_and_recovery_history_preserved(self):
        sale = self.confirmed()
        values = {f:getattr(sale,f) for f in FIELDS}
        values['fees'] = Decimal('4')
        sale = correct_sale(actor=self.actor, sale_id=sale.pk, revision=sale.revision,
            key=uuid4(), reason='Teste de revisão', values=values)
        sale = correct_cost(actor=self.actor, sale_id=sale.pk, revision=sale.revision,
            key=uuid4(), reason='Teste de custo', costs={sale.items.get().pk:Decimal('4')})
        sale = cancel(actor=self.actor, sale_id=sale.pk, reason='Teste de cancelamento')
        recover_sale(actor=self.actor, sale_id=sale.pk, revision=sale.revision,
            key=uuid4(), reason='Teste de recuperação', fees=Decimal('4'))
        sale_before = Sale.objects.values().get(pk=sale.pk)
        models = [SaleCorrection, SaleCostRevision, SaleRecovery]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('sales','0019_configuration_company_identity')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            originals = {}
            for current in models:
                model = state.get_model('sales',current.__name__)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[current.__name__] = (fields,list(model.objects.order_by('pk').values(*fields)))
            MigrationExecutor(connection).migrate(latest)
            for model in models:
                fields,rows = originals[model.__name__]
                self.assertTrue(rows)
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)),rows)
                self.assertEqual(set(model.objects.values_list('company_id',flat=True)),{1})
                with self.assertRaises(DatabaseError), transaction.atomic():
                    model.objects.update(reason='Alteração indevida')
            self.assertEqual(Sale.objects.values().get(pk=sale.pk),sale_before)
        finally:
            MigrationExecutor(connection).migrate(latest)
