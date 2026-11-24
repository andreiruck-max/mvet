from decimal import Decimal as D
from uuid import uuid4
from django.core import signing
from django.test import TestCase
from django.urls import reverse
from apps.core.models import Company
from apps.inventory.models import StockBalance, StockOperation, StockMovement
from apps.inventory.tests import StockFixtures, DAY
from apps.integrations.stock_comparison import local
from apps.products.models import Product
from . import selectors, drilldown


class StockOwnerConsumerTests(StockFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.original=self.op().movements.get()
        Company.objects.filter(pk=1).update(default_stock_location=self.loc)
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        StockBalance.objects.create(company_id=2,product=self.p,location=self.loc,
            quantity=D('100'),value=D('9900'),average_cost=D('99'))
        Product.objects.filter(pk=self.p.pk).update(quantity=D('110'),value=D('9950'))
        other=StockOperation.objects.create(company_id=2,actor=self.actor,date=DAY,
            kind='RECEIPT',key=uuid4(),reason='Projeção secundária sintética',fingerprint='owner-consumer')
        values={f.attname:getattr(self.original,f.attname) for f in StockMovement._meta.concrete_fields if not f.primary_key}
        values.update(company_id=2,operation_id=other.pk,cost_variance=D('999'))
        StockMovement.objects.create(**values)
        self.period={'start':DAY,'end':DAY}
        self.client.force_login(self.actor)

    def test_local_bling_snapshot_ignores_secondary_stock_and_revision(self):
        snapshot=local(self.p,self.loc)
        self.assertEqual(D(snapshot['quantity']),D('10'))
        self.assertEqual(D(snapshot['price']),D('6.75'))
        self.assertEqual(snapshot['last'],self.original.pk)

    def test_secondary_variance_does_not_enter_primary_dre_or_sources(self):
        result=selectors.dre(self.period)
        self.assertEqual(result['expenses']['OPERATING'],D('0'))
        token=signing.dumps({'kind':'inventory','label':'Estoque'},salt=drilldown.SALT)
        _, rows, total=drilldown.sources(token,self.period)
        self.assertEqual(rows,[])
        self.assertEqual(total,D('0'))

    def test_dashboard_stock_value_is_owned_position(self):
        response=self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['stock'],D('50'))
