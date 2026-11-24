from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, connections, transaction, close_old_connections
from django.test import TransactionTestCase
from apps.core.models import Company
from apps.products.models import Product
from .models import StockBalance, StockLocation, StockOperation
from .services import _apply, domain_lock
from .tests import StockFixtures, DAY


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL concurrency required')
class OwnerConcurrencyTests(StockFixtures, TransactionTestCase):
    def test_concurrent_receipts_keep_both_owner_costs_and_physical_sum(self):
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        start=Barrier(2,timeout=20)
        product_id,location_id,actor_id=self.p.pk,self.loc.pk,self.actor.pk

        def receive(owner,cost):
            close_old_connections()
            try:
                actor=get_user_model().objects.get(pk=actor_id)
                location=StockLocation.objects.get(pk=location_id)
                start.wait()
                for _ in range(5):
                    with transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute("SET LOCAL lock_timeout = '10s'")
                        domain_lock()
                        product=Product.objects.select_for_update().get(pk=product_id)
                        operation=StockOperation.objects.create(company_id=owner,actor=actor,
                            date=DAY,kind='RECEIPT',key=uuid4(),fingerprint='concurrent-owner',
                            reason='Recebimento concorrente sintético')
                        _apply(operation,product,location,D('2'),D('2')*cost,unit_cost=cost)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(receive,1,D('5')),pool.submit(receive,2,D('7'))]
            for future in futures:
                future.result(timeout=40)
        self.assertEqual(list(StockBalance.objects.filter(product_id=product_id).order_by('company_id')
            .values_list('company_id','quantity','value','average_cost')),
            [(1,D('10'),D('50'),D('5')),(2,D('10'),D('70'),D('7'))])
        self.assertEqual((self.fresh().quantity,self.p.value),(D('20'),D('120')))
        self.assertEqual(StockOperation.objects.count(),10)
        call_command('check_inventory')
