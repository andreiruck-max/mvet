from decimal import Decimal as D
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from .selectors import catalog, stock_totals, selected_location, location_values, kit_summary
from .planning import purchase_plan
from .tests import StockFixtures


class StockQueryScopeTests(StockFixtures, TestCase):
    def test_secondary_queries_do_not_fall_back_to_primary(self):
        self.op()
        calls=[lambda:catalog({},company_id=2),lambda:stock_totals([self.loc],company_id=2),
               lambda:selected_location({},company_id=2),lambda:location_values(self.p,company_id=2),
               lambda:kit_summary(self.p,company_id=2),
               lambda:purchase_plan(location=self.loc,zero_days=30,history_days=30,coverage_days=30,company_id=2)]
        for query in calls:
            with self.assertRaises(PermissionDenied):query()

    def test_local_catalog_and_total_include_other_locations(self):
        self.op()
        self.op('TRANSFER',quantity=D('2'),target_location_id=self.full.pk)
        row=catalog({'positive':'0'},self.loc,company_id=1).get(pk=self.p.pk)
        self.assertEqual(row.stock_quantity,D('8'))
        self.assertEqual(row.stock_cost,D('5'))
        rows,total=stock_totals([self.loc],company_id=1)
        self.assertEqual(rows[0]['value'],D('40'))
        self.assertEqual(total,D('50'))
        self.assertEqual(location_values(self.fresh()),{self.loc.pk:D('40'),self.full.pk:D('10')})
