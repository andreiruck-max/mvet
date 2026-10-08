from decimal import Decimal as D
from io import StringIO
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.sales.services import confirm, cancel
from apps.sales.recovery import recover_sale
from apps.reporting.selectors import dre
from .models import StockLocation, StockMovement
from .services import execute, reverse


class NegativeSalesTests(Fixture,TestCase):
    def sell(self,quantity='12',**changes):
        sale=self.draft(items=[(self.product.pk,D(quantity))],**changes)
        return confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)

    def balance(self,q,v,c):
        balance=self.product.balances.get(location=self.location)
        self.assertEqual((balance.quantity,balance.value,balance.average_cost),(D(q),D(v),D(c)))
        call_command('check_inventory',stdout=StringIO())

    def test_partial_and_full_replenishment_preserve_sale_and_recognize_variance(self):
        sale=self.sell();self.balance('-2','-10','5')
        self.assertEqual(sale.cmv,60)
        first=self.receive(self.product,D('1'),D('7'))
        self.balance('-1','-5','5');self.assertEqual(first.movements.get().cost_variance,2)
        second=self.receive(self.product,D('3'),D('8'))
        self.balance('2','16','8');self.assertEqual(second.movements.get().cost_variance,3)
        sale.refresh_from_db();self.assertEqual(sale.cmv,60)
        report=dre(dict(start=timezone.localdate(),end=timezone.localdate()))
        self.assertEqual(report['expenses']['OPERATING'],5)
        self.assertEqual(report['ebitda'],sale.contribution-5)

    def test_zero_balance_new_reference_and_lower_cost_variance(self):
        sale=self.sell();entry=self.receive(self.product,D('2'),D('3'))
        self.balance('0','0','3');self.assertEqual(entry.movements.get().cost_variance,-4)
        next_sale=self.sell('1',invoice_number='101')
        self.assertEqual(next_sale.cmv,3);self.balance('-1','-3','3')

    def test_free_bonus_covers_debt_without_rewriting_sale(self):
        sale=self.sell();entry=self.receive(self.product,D('3'),D('0'))
        self.balance('1','0','0');self.assertEqual(entry.movements.get().cost_variance,-10)
        sale.refresh_from_db();self.assertEqual(sale.cmv,60)

    def test_receipt_reversal_restores_debt_and_reverses_variance(self):
        self.sell();entry=self.receive(self.product,D('3'),D('7'))
        reverse(actor=self.actor,operation_id=entry.pk,key=uuid4(),date=timezone.localdate(),reason='Corrigir entrada')
        self.balance('-2','-10','5')
        self.assertEqual(sum(StockMovement.objects.values_list('cost_variance',flat=True)),0)

    def test_cancellation_recovery_and_new_cancel_after_different_receipt(self):
        sale=self.sell();self.receive(self.product,D('1'),D('7'))
        sale=cancel(actor=self.actor,sale_id=sale.pk,reason='Engano')
        self.balance('11','55','5')
        sale=recover_sale(actor=self.actor,sale_id=sale.pk,revision=sale.revision,key=uuid4(),fees=D('1'),reason='Recuperar')
        self.balance('-1','-5','5');self.assertEqual(sale.cmv,60)
        cancel(actor=self.actor,sale_id=sale.pk,reason='Cancelar novamente')
        self.balance('11','55','5')

    def test_missing_reference_never_borrows_other_depot_cost(self):
        other=StockLocation.objects.create(name='Sem histórico')
        sale=self.draft(location=other)
        with self.assertRaisesMessage(ValidationError,'sem custo de referência'):
            confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)
        execute(actor=self.actor,key=uuid4(),kind='REVALUE',date=timezone.localdate(),reason='Custo informado',product_id=self.product.pk,location_id=other.pk,quantity=D(0),cost=D('9'))
        sale=confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)
        self.assertEqual(sale.cmv,18)
        call_command('check_inventory',stdout=StringIO())

    def test_mixed_depots_net_zero_is_consistent_and_generic_shortage_still_blocks(self):
        self.sell('20')
        other=StockLocation.objects.create(name='Outro custo')
        execute(actor=self.actor,key=uuid4(),kind='RECEIPT',date=timezone.localdate(),reason='Outro depósito',product_id=self.product.pk,location_id=other.pk,quantity=D(10),cost=D(9))
        self.product.refresh_from_db();self.assertEqual((self.product.quantity,self.product.value,self.product.average_cost),(0,40,9))
        call_command('check_inventory',stdout=StringIO())
        with self.assertRaises(ValidationError):
            execute(actor=self.actor,key=uuid4(),kind='ISSUE',date=timezone.localdate(),reason='Saída avulsa',product_id=self.product.pk,location_id=self.location.pk,quantity=D(1))

    def test_purchase_receipt_and_cancel_restore_negative_balance(self):
        from apps.purchases import services as purchases
        from apps.purchases.models import Supplier
        self.sell()
        supplier=Supplier.objects.create(legal_name='Fornecedor sintético')
        date=timezone.localdate()
        data=dict(supplier=supplier,document='900',series='1',date=date,location=self.location,discount=D(0),freight=D(0),other_costs=D(0),notes='')
        purchase=purchases.save_draft(actor=self.actor,key=uuid4(),data=data,items=[(self.product.pk,D(3),D(7))],installments=[(date,D(21),'')])
        purchase=purchases.confirm(actor=self.actor,purchase_id=purchase.pk,revision=purchase.revision)
        purchase=purchases.receive(actor=self.actor,purchase_id=purchase.pk,date=date,revision=purchase.revision)
        self.balance('1','7','7')
        purchases.cancel(actor=self.actor,purchase_id=purchase.pk,reason='Estorno de teste')
        self.balance('-2','-10','5')
        self.assertEqual(sum(StockMovement.objects.values_list('cost_variance',flat=True)),0)
