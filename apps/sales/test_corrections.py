from decimal import Decimal as D
from uuid import uuid4
from unittest import skipUnless
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import connection,transaction,DatabaseError
from django.test import TestCase
from django.urls import reverse
from apps.inventory.models import StockMovement
from apps.reporting.selectors import sales_summary
from .tests import Fixture
from .models import Sale,SaleCorrection
from .corrections import correct_sale,FIELDS
from .services import cancel
from .recovery import recover_sale

class CorrectionTests(Fixture,TestCase):
    def correct(self,sale,**changes):
        values={name:getattr(sale,name) for name in FIELDS};values.update(changes)
        return correct_sale(actor=self.actor,sale_id=sale.pk,revision=sale.revision,key=uuid4(),reason='Corrigir digitação',values=values)

    def test_fees_preserve_stock_tax_and_update_reports(self):
        sale=self.confirmed(fees=D('41.62'));count=StockMovement.objects.count();cmv=sale.cmv;tax=sale.tax_snapshot;contribution=sale.contribution
        sale=self.correct(sale,fees=D('20.81'))
        self.assertEqual(StockMovement.objects.count(),count);self.assertEqual(sale.cmv,cmv);self.assertEqual(sale.tax_snapshot,tax)
        self.assertEqual(sale.contribution,contribution+D('20.81'))
        self.assertEqual(sales_summary(Sale.objects.all())['fees'],D('20.81'))
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse('dashboard')).context['totals']['fees'],D('20.81'))
        self.assertEqual(self.client.get(reverse('dre')).context['report']['sales']['fees'],D('20.81'))
        self.assertContains(self.client.get(reverse('sale_detail',args=[sale.pk])),'Corrigir digitação')
        cancel(actor=self.actor,sale_id=sale.pk,reason='Teste');self.product.refresh_from_db();self.assertEqual(self.product.quantity,10)

    def test_revenue_uses_historic_tax_and_stale_or_nonmaster_rejected(self):
        sale=self.confirmed();revision=sale.revision
        self.rule.rate=D(12);self.rule.save()
        sale=self.correct(sale,discount=D(0));self.assertEqual(sale.tax_amount,D('5.25'))
        values={name:getattr(sale,name) for name in FIELDS};values['fees']=D(1)
        with self.assertRaises(ValidationError):correct_sale(actor=self.actor,sale_id=sale.pk,revision=revision,key=uuid4(),reason='Antiga',values=values)
        with self.assertRaises(PermissionDenied):correct_sale(actor=self.operator,sale_id=sale.pk,revision=sale.revision,key=uuid4(),reason='Teste',values=values)
        self.client.force_login(self.operator);self.assertEqual(self.client.get(reverse('sale_correct',args=[sale.pk])).status_code,403)

    def test_duplicate_submit_and_recovery_then_correction(self):
        sale=self.confirmed();sale=cancel(actor=self.actor,sale_id=sale.pk,reason='Engano')
        sale=recover_sale(actor=self.actor,sale_id=sale.pk,revision=sale.revision,key=uuid4(),fees=D(3),reason='Recuperar')
        values={name:getattr(sale,name) for name in FIELDS};values['shipping_paid']=D(4)
        kwargs=dict(actor=self.actor,sale_id=sale.pk,revision=sale.revision,key=uuid4(),reason='Frete corrigido',values=values)
        correct_sale(**kwargs);correct_sale(**kwargs)
        self.assertEqual(SaleCorrection.objects.count(),1)
        values['fees']=D(8)
        with self.assertRaises(ValidationError):correct_sale(**kwargs)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL trigger protection')
    def test_direct_updates_and_audit_edits_blocked(self):
        sale=self.correct(self.confirmed(),fees=D(1))
        with self.assertRaises(DatabaseError),transaction.atomic():Sale.objects.filter(pk=sale.pk).update(fees=D(2))
        with self.assertRaises(DatabaseError),transaction.atomic():SaleCorrection.objects.filter(sale=sale).update(reason='Mutação')
