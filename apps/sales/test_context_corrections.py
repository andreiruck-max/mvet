from decimal import Decimal as D
from uuid import uuid4
from unittest import skipUnless
from django.core.exceptions import ValidationError
from django.db import connection, transaction, DatabaseError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.inventory.models import StockLocation, StockMovement, StockOperation, StockBalance
from apps.inventory.services import execute
from apps.reporting.selectors import sales_summary
from .tests import Fixture
from .models import Sale, SalesChannel, SaleCorrection
from .corrections import correct_sale, FIELDS
from .services import cancel
from .recovery import recover_sale


class ContextCorrectionTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.other = StockLocation.objects.create(name='Full teste')
        self.other_channel = SalesChannel.objects.create(name='Canal Full teste')
        execute(actor=self.actor,key=uuid4(),kind='RECEIPT',date=timezone.localdate(),reason='Estoque destino',product_id=self.product.pk,location_id=self.other.pk,quantity=D(10),cost=D(8))

    def arguments(self, sale, **changes):
        return dict(actor=self.actor,sale_id=sale.pk,revision=sale.revision,key=uuid4(),reason='Corrigir canal e depósito',values={f:getattr(sale,f) for f in FIELDS},**changes)

    def test_channel_only_updates_report_without_stock(self):
        sale=self.confirmed();count=StockMovement.objects.count()
        sale=correct_sale(**self.arguments(sale,channel_id=self.other_channel.pk))
        self.assertEqual(sale.channel_id,self.other_channel.pk)
        self.assertEqual(StockMovement.objects.count(),count)
        self.assertEqual(sales_summary(Sale.objects.filter(channel=self.other_channel))['count'],1)
        self.assertEqual(sales_summary(Sale.objects.filter(channel=self.channel))['count'],0)
        self.client.force_login(self.actor)
        self.assertContains(self.client.get(reverse('sale_detail',args=[sale.pk])),'Canal Full teste')

    def test_relocation_preserves_snapshots_and_can_cancel_recover_relocate(self):
        sale=self.confirmed();oldop=sale.stock_operation_id;cmv=sale.cmv;tax=sale.tax_snapshot
        item=sale.items.get();item_snapshot=(item.cmv,item.unit_cost,item.consumptions.get().movement_id)
        args=self.arguments(sale,channel_id=self.other_channel.pk,location_id=self.other.pk)
        sale=correct_sale(**args);count=StockMovement.objects.count()
        correct_sale(**args)
        self.assertEqual(StockMovement.objects.count(),count)
        self.assertEqual((sale.cmv,sale.tax_snapshot),(cmv,tax))
        item.refresh_from_db();self.assertEqual((item.cmv,item.unit_cost,item.consumptions.get().movement_id),item_snapshot)
        self.assertEqual(sale.stock_operation.reversal_of.reversal_of_id,oldop)
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.location).quantity,10)
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.other).quantity,8)
        self.assertEqual(sale.stock_operation.movements.get().cost_variance,D(6))
        self.assertEqual(SaleCorrection.objects.count(),1)
        with self.assertRaises(ValidationError):correct_sale(**dict(args,location_id=self.location.pk))
        sale=cancel(actor=self.actor,sale_id=sale.pk,reason='Teste após correção')
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.other).quantity,10)
        sale=recover_sale(actor=self.actor,sale_id=sale.pk,revision=sale.revision,key=uuid4(),fees=sale.fees,reason='Recuperação após correção')
        sale=correct_sale(**self.arguments(sale,location_id=self.location.pk))
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.location).quantity,8)
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.other).quantity,10)
        self.assertEqual(sale.cmv,cmv)
        from django.core.management import call_command
        from io import StringIO
        call_command('check_inventory',stdout=StringIO())

    def test_negative_destination_uses_its_reference_and_preserves_ledger(self):
        sale=self.confirmed(items=[(self.product.pk,D(12))])
        correct_sale(**self.arguments(sale,location_id=self.other.pk))
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.other).quantity,-2)
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.location).quantity,10)
        from django.core.management import call_command
        from io import StringIO
        call_command('check_inventory',stdout=StringIO())

    def test_kit_relocation_uses_original_components(self):
        from apps.products.models import Product
        from apps.products.services import set_components
        kit=Product.objects.create(sku='CONTEXT-KIT',name='Kit sintético',kind='KIT')
        set_components(actor=self.actor,kit_id=kit.pk,items=[(self.product.pk,D(2))])
        sale=self.confirmed(items=[(kit.pk,D(2))])
        set_components(actor=self.actor,kit_id=kit.pk,items=[(self.product.pk,D(3))])
        sale=correct_sale(**self.arguments(sale,location_id=self.other.pk))
        self.assertEqual(sale.stock_operation.movements.get().quantity,-4)
        self.assertEqual(StockBalance.objects.get(product=self.product,location=self.other).quantity,6)

    def test_missing_cost_inactive_target_and_stale_revision_roll_back(self):
        sale=self.confirmed();empty=StockLocation.objects.create(name='Sem referência')
        moves=StockMovement.objects.count();operations=StockOperation.objects.count();oldop=sale.stock_operation_id
        with self.assertRaises(ValidationError):correct_sale(**self.arguments(sale,location_id=empty.pk))
        self.other.active=False;self.other.save()
        with self.assertRaises(ValidationError):correct_sale(**self.arguments(sale,location_id=self.other.pk))
        args=self.arguments(sale,channel_id=self.other_channel.pk);args['revision']-=1
        with self.assertRaises(ValidationError):correct_sale(**args)
        sale.refresh_from_db();self.assertEqual(sale.stock_operation_id,oldop)
        self.assertEqual(StockMovement.objects.count(),moves);self.assertEqual(StockOperation.objects.count(),operations)
        self.assertFalse(SaleCorrection.objects.exists())

    def test_post_corrects_context_and_values_atomically(self):
        sale=self.confirmed();self.client.force_login(self.actor)
        data={f:str(getattr(sale,f)) for f in FIELDS}
        data.update(channel=self.other_channel.pk,location=self.other.pk,fees='20.81',revision=sale.revision,key=str(uuid4()),reason='Teste completo')
        response=self.client.post(reverse('sale_correct',args=[sale.pk]),data)
        self.assertEqual(response.status_code,302)
        sale.refresh_from_db();self.assertEqual((sale.channel_id,sale.location_id,sale.fees),(self.other_channel.pk,self.other.pk,D('20.81')))
        self.assertContains(self.client.get(reverse('sale_detail',args=[sale.pk])),'Full teste')

    @skipUnless(connection.vendor=='postgresql','PostgreSQL trigger')
    def test_direct_context_and_stock_pointer_changes_are_blocked(self):
        sale=self.confirmed()
        for values in ({'channel_id':self.other_channel.pk},{'location_id':self.other.pk},{'stock_operation_id':None}):
            with self.assertRaises(DatabaseError),transaction.atomic():Sale.objects.filter(pk=sale.pk).update(**values)
        args=self.arguments(sale,location_id=self.other.pk)
        correct_sale(**args)
        with self.assertRaises(DatabaseError),transaction.atomic():SaleCorrection.objects.filter(sale=sale).update(after={})

    @skipUnless(connection.vendor=='postgresql','PostgreSQL trigger')
    def test_audit_record_without_stock_reversal_cannot_relocate(self):
        from .corrections import snapshot
        sale=self.confirmed();before=snapshot(sale);after=dict(before,location_id=self.other.pk)
        key=uuid4()
        SaleCorrection.objects.create(key=key,sale=sale,actor=self.actor,reason='Registro sem estoque',before_revision=sale.revision,before=before,after=after)
        with self.assertRaises(DatabaseError),transaction.atomic():
            with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.sale_correction', %s, true)",[str(key)])
            Sale.objects.filter(pk=sale.pk).update(location_id=self.other.pk,revision=sale.revision+1)
