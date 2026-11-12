from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import PermissionDenied, ValidationError
from .tests import Fixture
from .models import DuePayment, FinancialOperation, FinancialTitle
from .due_payments import configure, tick
from . import selectors


class DuePaymentTests(Fixture,TestCase):
    def schedule(self,title,**kwargs):
        title.refresh_from_db()
        return configure(actor=self.admin,title_id=title.pk,account_id=self.a.pk,enabled=True,revision=title.revision,**kwargs)

    def test_runs_at_due_date_once_after_partial_payment(self):
        due=self.today+timedelta(days=2);t=self.title(due_date=due)
        self.schedule(t);tick();self.assertFalse(FinancialOperation.objects.exists())
        self.settle(t,principal=D(40),actual=D(40))
        with patch('django.utils.timezone.localdate',return_value=due):tick();tick()
        t.refresh_from_db();self.assertEqual(t.settled,100)
        self.assertEqual(list(t.operations.order_by('date').values_list('principal',flat=True)),[D(40),D(60)])
        obj=DuePayment.objects.get(title=t);self.assertFalse(obj.enabled);self.assertEqual(obj.operation.date,due)
        self.assertEqual(selectors.cash_summary(self.today,due)['actual'],900)

    def test_cancel_schedule_and_permission_revocation(self):
        t=self.title();obj=self.schedule(t);t.refresh_from_db()
        configure(actor=self.admin,title_id=t.pk,account_id=None,enabled=False,revision=t.revision)
        tick();self.assertFalse(t.operations.exists())
        self.schedule(t);self.admin.is_active=False;self.admin.save()
        tick();obj.refresh_from_db();self.assertFalse(obj.enabled);self.assertIn('Permissão',obj.message)
        self.assertFalse(t.operations.exists())

    def test_late_worker_preserves_due_date_and_stale_submission_rejected(self):
        t=self.title();self.schedule(t)
        with self.assertRaises(ValidationError):configure(actor=self.admin,title_id=t.pk,account_id=self.a.pk,enabled=True,revision=0)
        with patch('django.utils.timezone.localdate',return_value=self.today+timedelta(days=3)):tick()
        self.assertEqual(t.operations.get().date,self.today)
        with self.assertRaises(PermissionDenied):configure(actor=self.seller,title_id=t.pk,account_id=self.a.pk,enabled=True,revision=0)

    def test_get_never_pays_and_post_requires_csrf(self):
        t=self.title();self.client.force_login(self.admin)
        endpoint=reverse('financial_due_payment',args=[t.pk])
        response=self.client.get(endpoint+'?_modal=1');self.assertEqual(response.status_code,200)
        self.assertFalse(DuePayment.objects.exists())
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.admin)
        self.assertEqual(csrf.post(endpoint,{'enabled':'on','account':self.a.pk,'revision':0}).status_code,403)

    def test_account_and_title_cancellation_do_not_trigger_duplicate_payment(self):
        from . import services
        t=self.title();obj=self.schedule(t)
        services.cancel_title(actor=self.admin,pk=t.pk,reason='Cancelado')
        tick();obj.refresh_from_db();self.assertFalse(obj.enabled);self.assertFalse(t.operations.exists())
