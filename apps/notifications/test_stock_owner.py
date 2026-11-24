from decimal import Decimal as D
from django.test import TestCase
from django.utils import timezone
from apps.core.models import Company
from apps.products.models import CompanyProductPolicy
from apps.inventory.models import StockBalance
from apps.inventory.tests import StockFixtures
from .models import AlertConfiguration
from .services import conditions


class StockOwnerAlertTests(StockFixtures, TestCase):
    def setUp(self):
        super().setUp()
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        CompanyProductPolicy.objects.create(company_id=1,product=self.p,minimum=D('5'))
        self.config=AlertConfiguration(stock=True,margin=False,due=False,backup=False)

    def alerts(self):
        return [row for row in conditions(self.config,timezone.now()) if row[0]=='STOCK']

    def test_secondary_abundance_does_not_hide_missing_primary_stock(self):
        StockBalance.objects.create(company_id=2,product=self.p,location=self.loc,
            quantity=D('100'),value=D('500'),average_cost=D('5'))
        self.p.quantity=D('100');self.p.save(update_fields=['quantity'])
        rows=self.alerts()
        self.assertEqual([row[1] for row in rows],[self.p.pk])
        self.assertIn('0 UN no total dos estoques da empresa',rows[0][3])

    def test_secondary_deficit_does_not_create_false_primary_alert(self):
        self.op()
        StockBalance.objects.create(company_id=2,product=self.p,location=self.loc,
            quantity=D('-9'),value=D('-45'),average_cost=D('5'))
        self.p.quantity=D('1');self.p.save(update_fields=['quantity'])
        self.assertEqual(self.alerts(),[])
        self.op('TRANSFER',quantity=D('5'),target_location_id=self.full.pk)
        self.assertEqual(self.alerts(),[])
