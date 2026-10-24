from decimal import Decimal as D
from uuid import uuid4
from django.contrib.auth.models import User, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase
from django.urls import reverse as url
from .tests import StockFixtures, DAY
from .models import StockBalance, StockOperation, StockMovement
from .services import transfer_batch, reverse
from apps.products.models import Product


class BatchTransferTests(StockFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.second = Product.objects.create(sku='P2', name='Segundo produto')
        self.op()
        self.op(product_id=self.second.pk, cost=D('7'))
        self.data = dict(actor=self.actor,key=uuid4(),date=DAY,reason='Envio Full sintético',
            location_id=self.loc.pk,target_location_id=self.full.pk,
            items=[(self.p.pk,D('3')),(self.second.pk,D('4'))])

    def test_atomic_transfer_replay_and_reversal(self):
        op = transfer_batch(**self.data)
        self.assertEqual(op.movements.count(),4)
        self.assertEqual(transfer_batch(**self.data).pk,op.pk)
        for p,qty,value in [(self.p,3,15),(self.second,4,28)]:
            balance=StockBalance.objects.get(product=p,location=self.full)
            self.assertEqual(balance.quantity,qty);self.assertEqual(balance.value,value)
            p.refresh_from_db();self.assertEqual(p.quantity,10)
        with self.assertRaises(ValidationError):
            transfer_batch(**{**self.data,'items':[(self.p.pk,D('2'))]})
        reverse(actor=self.actor,operation_id=op.pk,key=uuid4(),date=DAY,reason='Corrigir envio')
        self.assertFalse(StockBalance.objects.filter(location=self.full).exclude(quantity=0).exists())

    def test_invalid_batch_has_no_partial_movements(self):
        count=StockMovement.objects.count()
        for changes in [
            {'items':[(self.p.pk,D('3')),(self.second.pk,D('11'))]},
            {'items':[(self.p.pk,D('3')),(self.p.pk,D('1'))]},
            {'items':[(self.p.pk,D('0'))]},
            {'items':[]}, {'target_location_id':self.loc.pk},
            {'items':[(999999,D('1'))]},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                transfer_batch(**{**self.data,**changes})
            self.assertEqual(StockMovement.objects.count(),count)
        self.second.active=False;self.second.save()
        with self.assertRaises(ValidationError):transfer_batch(**self.data)
        self.assertEqual(StockMovement.objects.count(),count)

    def test_permissions_and_form_submission(self):
        user=User.objects.create_user('transfer-only')
        self.client.force_login(user)
        self.assertEqual(self.client.get(url('transfer_batch')).status_code,403)
        with self.assertRaises(PermissionDenied):transfer_batch(**{**self.data,'actor':user})
        user.user_permissions.add(*Permission.objects.filter(codename__in=['operate_stock','transfer_stock','view_stock']))
        user=User.objects.get(pk=user.pk)
        self.client.force_login(user)
        self.assertContains(self.client.get(url('transfer_batch')),'Confirmar transferência de todos')
        data={'key':str(uuid4()),'date':DAY.isoformat(),'location':self.loc.pk,'target_location':self.full.pk,'reason':'Envio teste',
            'form-TOTAL_FORMS':'2','form-INITIAL_FORMS':'0',
            'form-0-product':self.p.pk,'form-0-quantity':'2',
            'form-1-product':self.second.pk,'form-1-quantity':'3'}
        response=self.client.post(url('transfer_batch'),data)
        self.assertEqual(response.status_code,302)
        op=StockOperation.objects.get(key=data['key']);self.assertEqual(op.movements.count(),4)
        self.assertEqual(self.client.post(url('transfer_batch'),data).status_code,302)
        data['key']=str(uuid4());data['form-1-quantity']='100'
        self.assertContains(self.client.post(url('transfer_batch'),data),'estoque insuficiente')
        self.assertFalse(StockOperation.objects.filter(key=data['key']).exists())
