from decimal import Decimal
from uuid import uuid4
from django.core.exceptions import PermissionDenied
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from apps.core.models import Company
from apps.inventory.models import StockOperation
from .models import Sale, SaleConsumption, SalesChannel, TaxRule
from .tests import Fixture


class SaleOwnerLinkTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        self.foreign_channel=SalesChannel.objects.create(company_id=2,name='Canal secundário')
        self.foreign_rule=TaxRule.objects.create(company_id=2,name='Imposto secundário',rate=4,
                                               base='REVENUE',starts_on=self.company.cutover_date)
        self.foreign_operation=StockOperation.objects.create(company_id=2,actor=self.actor,
            kind='SALE_OUT',date=timezone.localdate(),reason='Teste de vínculo',fingerprint='synthetic')

    def test_draft_cannot_link_other_company_by_direct_update(self):
        sale=self.draft()
        original=Sale.objects.values().get(pk=sale.pk)
        for field,value in [('channel_id',self.foreign_channel.pk),('tax_rule_id',self.foreign_rule.pk),
                            ('stock_operation_id',self.foreign_operation.pk),
                            ('return_operation_id',self.foreign_operation.pk)]:
            with self.subTest(field=field), self.assertRaisesMessage(IntegrityError,'another company'), transaction.atomic():
                Sale.objects.filter(pk=sale.pk).update(**{field:value})
        self.assertEqual(Sale.objects.values().get(pk=sale.pk),original)

    def test_direct_insert_cannot_link_foreign_configuration(self):
        for field,value in [('channel',self.foreign_channel),('tax_rule',self.foreign_rule)]:
            with self.subTest(field=field), self.assertRaisesMessage(IntegrityError,'another company'), transaction.atomic():
                Sale.objects.create(created_by=self.actor,**{field:value})
        self.assertFalse(Sale.objects.exists())

    def test_consumption_cannot_record_another_owners_stock_movement(self):
        from apps.inventory.services import _apply
        item = self.draft().items.get()
        self.product.refresh_from_db()
        receipt = StockOperation.objects.create(company_id=2, actor=self.actor, kind='RECEIPT',
            date=timezone.localdate(), reason='Teste de origem do estoque', fingerprint='synthetic-receipt')
        _apply(receipt, self.product, self.location, Decimal('2'), Decimal('10'))
        movement = _apply(self.foreign_operation, self.product, self.location, Decimal('-1'), Decimal('-5'))
        with self.assertRaisesMessage(IntegrityError, 'another company'), transaction.atomic():
            SaleConsumption.objects.create(item=item, movement=movement, company_id=item.company_id)
        self.assertFalse(SaleConsumption.objects.exists())

    def test_primary_draft_with_optional_links_empty_still_confirms(self):
        from .services import confirm, cancel
        sale=self.draft()
        Sale.objects.filter(pk=sale.pk).update(tax_rule=None,tax_override=0,tax_reason='Teste sintético')
        sale=confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)
        self.assertEqual(sale.stock_operation.company_id,sale.company_id)
        self.assertEqual(sale.cmv,10)
        sale=cancel(actor=self.actor,sale_id=sale.pk,reason='Teste de estorno')
        self.assertEqual(sale.return_operation.company_id,sale.company_id)

    def test_group_cannot_create_edit_or_replay_draft(self):
        from apps.accounts.company_context import CompanyScope
        from .services import save_draft
        args = dict(actor=self.actor, key=uuid4(), data=self.data(), items=[(self.product.pk, Decimal('1'))])
        sale = save_draft(**args)
        original = Sale.objects.values().get(pk=sale.pk)
        self.actor._mvet_company_scope = CompanyScope((1,), group=True)
        for extra in ({'key':uuid4()}, {}, {'sale_id':sale.pk, 'revision':sale.revision}):
            with self.subTest(extra=extra), self.assertRaises(PermissionDenied):
                save_draft(**dict(args, **extra))
        self.assertEqual(list(Sale.objects.values()), [original])


class SaleOwnerMigrationTests(Fixture, TransactionTestCase):
    def test_existing_mixed_draft_stops_migration_without_repair(self):
        sale = self.draft()
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        channel = SalesChannel.objects.create(company_id=2, name='Canal de homologação')
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            MigrationExecutor(connection).migrate([('sales','0022_company_sales_channels')])
            Sale.objects.filter(pk=sale.pk).update(channel=channel)
            with self.assertRaisesMessage(RuntimeError, 'vínculo empresarial inconsistente'):
                MigrationExecutor(connection).migrate([('sales','0023_sale_owner_integrity')])
            self.assertEqual(Sale.objects.get(pk=sale.pk).channel_id, channel.pk)
        finally:
            Sale.objects.filter(pk=sale.pk).update(channel=self.channel)
            MigrationExecutor(connection).migrate(latest)
