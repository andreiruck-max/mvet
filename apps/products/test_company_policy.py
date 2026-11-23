from decimal import Decimal as D
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from apps.accounts.company_context import CompanyScope
from apps.core.models import Company
from apps.inventory.tests import StockFixtures
from apps.inventory.selectors import catalog
from .models import Product, CompanyProductPolicy
from .pricing import configure_fixed_price, configure_pricing, sale_price
from .services import save_product


class CompanyPolicyTests(StockFixtures, TestCase):
    def test_primary_edits_keep_legacy_and_policy_consistent(self):
        save_product(actor=self.actor,pk=self.p.pk,data={'minimum':D('12')})
        configure_pricing(actor=self.actor,product_id=self.p.pk,markup=D('20'))
        configure_fixed_price(actor=self.actor,product_id=self.p.pk,price=D('8.50'))
        policy=CompanyProductPolicy.objects.get(company_id=1,product=self.p)
        self.p.refresh_from_db()
        self.assertEqual((policy.minimum,policy.markup,policy.fixed_sale_price),(D('12'),D('20'),D('8.50')))
        self.assertEqual(sale_price(self.p,D('5'),D('35')),D('8.50'))
        configure_fixed_price(actor=self.actor,product_id=self.p.pk,price=None)
        self.assertEqual(sale_price(self.p,D('5'),D('35')),D('6'))
        configure_pricing(actor=self.actor,product_id=self.p.pk,markup=None)
        self.assertEqual(sale_price(self.p,D('5'),D('35')),D('6.75'))

    def test_same_sku_can_hold_distinct_settings_without_cross_write(self):
        agro,_=Company.objects.get_or_create(pk=2,defaults={'active':False})
        second=CompanyProductPolicy.objects.create(company=agro,product=self.p,minimum=D('3'),markup=D('70'),fixed_sale_price=D('99'))
        configure_fixed_price(actor=self.actor,product_id=self.p.pk,price=D('8'))
        second.refresh_from_db()
        self.assertEqual((second.minimum,second.markup,second.fixed_sale_price),(D('3'),D('70'),D('99')))
        self.assertEqual(Product.objects.filter(sku=self.p.sku).count(),1)
        with self.assertRaises(PermissionDenied):sale_price(self.p,D('5'),D('35'),company_id=2)
        with self.assertRaises(IntegrityError),transaction.atomic():
            CompanyProductPolicy.objects.create(company=agro,product=self.p)

    def test_group_cannot_edit_shared_or_primary_settings(self):
        self.actor._mvet_company_scope=CompanyScope((1,),group=True)
        with self.assertRaises(PermissionDenied):configure_fixed_price(actor=self.actor,product_id=self.p.pk,price=D('8'))
        with self.assertRaises(PermissionDenied):configure_pricing(actor=self.actor,markup=D('8'))
        with self.assertRaises(PermissionDenied):save_product(actor=self.actor,pk=self.p.pk,data={'minimum':D('2')})
        self.assertFalse(CompanyProductPolicy.objects.exists())

    def test_catalog_uses_company_minimum_and_prefetches_prices(self):
        self.op()
        CompanyProductPolicy.objects.create(company_id=1,product=self.p,minimum=D('11'),fixed_sale_price=D('9'))
        row=catalog({'low':'1'},self.loc).get(pk=self.p.pk)
        self.assertEqual(row.commercial_minimum,D('11'))
        with self.assertNumQueries(0):self.assertEqual(sale_price(row,D('5'),D('35')),D('9'))


class CompanyPolicyMigrationTests(TransactionTestCase):
    def test_migration_preserves_all_product_fields_and_copies_only_primary(self):
        Company.objects.get_or_create(pk=1)
        executor=MigrationExecutor(connection)
        latest=executor.loader.graph.leaf_nodes()
        before=[('products','0005_product_product_fixed_price_nonnegative')]
        try:
            executor.migrate(before)
            state=executor.loader.project_state(before).apps
            Legacy=state.get_model('products','Product')
            Legacy.objects.create(sku='POLICY-HISTORY',name='Sintético',minimum=D('1.875'),markup=D('0'),fixed_sale_price=D('0'))
            Legacy.objects.create(sku='POLICY-INHERIT',name='Herdado',active=False)
            rows=list(Legacy.objects.order_by('pk').values())
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(list(Product.objects.order_by('pk').values()),rows)
            for row in rows:
                policy=CompanyProductPolicy.objects.get(company_id=1,product_id=row['id'])
                for field in ('minimum','markup','fixed_sale_price'):
                    self.assertEqual(getattr(policy,field),row[field])
            self.assertFalse(CompanyProductPolicy.objects.exclude(company_id=1).exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
