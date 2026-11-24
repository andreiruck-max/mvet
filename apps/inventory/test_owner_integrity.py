from unittest import skipUnless
from uuid import uuid4
from django.db import connection, transaction, DatabaseError
from django.test import TestCase
from apps.core.models import Company
from .models import StockMovement, StockOperation
from .tests import StockFixtures, DAY


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL triggers required')
class StockOwnerIntegrityTests(StockFixtures, TestCase):
    def setUp(self):
        super().setUp()
        Company.objects.get_or_create(pk=2,defaults={'active':False})

    def test_insert_cannot_attach_movement_to_another_company_operation(self):
        original=self.op().movements.get()
        values={field.attname:getattr(original,field.attname)
                for field in StockMovement._meta.concrete_fields if not field.primary_key}
        values['company_id']=2
        with self.assertRaisesMessage(DatabaseError,'Stock movement owner differs'), transaction.atomic():
            StockMovement.objects.create(**values)
        self.assertEqual(StockMovement.objects.count(),1)

    def test_reversal_cannot_change_source_owner(self):
        original=self.op()
        with self.assertRaisesMessage(DatabaseError,'Stock reversal owner differs'), transaction.atomic():
            StockOperation.objects.create(company_id=2,actor=self.actor,date=DAY,
                kind='REVERSAL',key=uuid4(),fingerprint='cross-owner',
                reason='Tentativa sintética',reversal_of=original)
        self.assertEqual(StockOperation.objects.count(),1)
