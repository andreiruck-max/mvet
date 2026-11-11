from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.sales.models import Sale
from apps.finance.models import FinancialTitle
from apps.inventory.models import StockMovement
from .models import BlingConnection, BlingSchedule, InvoiceImport
from .scheduling import configure, tick, process_page, LOCK_ID
from .tests import payload, ISSUER


def result(**changes):
    return SimpleNamespace(**dict(dict(message='', errors=0, processed=2, has_more=False), **changes))


class ScheduleTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser('scheduler-owner')
        self.conn = BlingConnection.objects.create(pk=1, issuer=ISSUER, tokens='synthetic-not-a-real-token')

    def config(self, kind='SALE', **changes):
        return configure(actor=self.actor, kind=kind, data=dict(
            dict(enabled=True, interval_hours=1, lookback_days=7), **changes))

    def due(self, obj):
        BlingSchedule.objects.filter(pk=obj.pk).update(next_run_at=timezone.now()-timedelta(seconds=1))

    def test_disabled_default_no_requests_and_heartbeat(self):
        with patch('apps.integrations.bling.sync_page') as sync:
            self.assertFalse(tick())
            sync.assert_not_called()
        self.assertEqual(BlingSchedule.objects.count(), 2)
        self.assertTrue(all(s.worker_online and not s.enabled for s in BlingSchedule.objects.all()))

    def test_pages_resume_and_purchase_statuses_then_wait_interval(self):
        obj = self.config('PURCHASE')
        with patch('apps.integrations.bling.sync_page', side_effect=[result(has_more=True), result(), result()]) as sync:
            tick(); obj.refresh_from_db()
            self.assertEqual(obj.cursor['page'], 2)
            self.assertEqual(obj.cursor['status'], 0)
            self.due(obj); tick(); obj.refresh_from_db()
            self.assertEqual(obj.cursor['page'], 1)
            self.assertEqual(obj.cursor['status'], 1)
            self.due(obj); tick(); obj.refresh_from_db()
            self.assertEqual(obj.cursor, {})
            self.assertEqual(obj.processed, 6)
            self.assertIsNotNone(obj.last_finished_at)
            self.assertGreater(obj.next_run_at, timezone.now()+timedelta(minutes=59))
            self.assertFalse(tick())
            self.assertEqual([c.kwargs['source_status'] for c in sync.call_args_list], [5,5,7])
            self.assertEqual(sync.call_args.kwargs['time_budget'], 300)

    def test_failure_preserves_page_and_retries_without_blocking_other_kind(self):
        sale = self.config()
        purchase = self.config('PURCHASE')
        with patch('apps.integrations.bling.sync_page', side_effect=[result(message='Falha temporária',errors=1),result()]) as sync:
            tick(); sale.refresh_from_db()
            self.assertEqual(sale.cursor['page'], 1)
            self.assertGreater(sale.next_run_at, timezone.now()+timedelta(minutes=4))
            tick()
            self.assertEqual(sync.call_args.kwargs['kind'], 'PURCHASE')
        self.due(sale)
        with patch('apps.integrations.bling.sync_page', return_value=result()) as sync:
            tick()
            self.assertEqual(sync.call_args.kwargs['page'], 1)

    def test_configuration_during_page_does_not_get_overwritten(self):
        obj = self.config()
        def disable(**kwargs):
            self.config(enabled=False)
            return result(has_more=True)
        with patch('apps.integrations.bling.sync_page', side_effect=disable):
            tick()
        obj.refresh_from_db()
        self.assertFalse(obj.enabled)
        self.assertEqual(obj.cursor, {})
        self.assertIsNone(obj.next_run_at)

    def test_revoked_actor_stops_schedule_without_remote_calls(self):
        obj = self.config()
        User.objects.filter(pk=self.actor.pk).update(is_active=False)
        with patch('apps.integrations.bling.read') as read:
            tick(); read.assert_not_called()
        obj.refresh_from_db(); self.assertFalse(obj.enabled)

    def test_second_worker_cannot_enter(self):
        self.config()
        other = connection.copy()
        try:
            with other.cursor() as db:
                db.execute('SELECT pg_advisory_lock(%s)', [LOCK_ID])
            with patch('apps.integrations.bling.sync_page') as sync:
                self.assertFalse(tick()); sync.assert_not_called()
        finally:
            with other.cursor() as db:
                db.execute('SELECT pg_advisory_unlock(%s)', [LOCK_ID])
            other.close()

    def test_actual_staging_is_idempotent_and_never_confirms(self):
        obj = self.config()
        doc = payload()
        def read(path):
            if path.startswith('/nfe?'):
                return {'data':[{'id':1000}]} if 'situacao=5' in path else {'data':[]}
            return {'data':doc}
        with patch('apps.integrations.bling.read', side_effect=read), patch('apps.integrations.bling.enrich', side_effect=lambda p:p):
            tick(); self.due(obj); tick()
        self.assertEqual(InvoiceImport.objects.count(), 1)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(FinancialTitle.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_settings_permissions_validation_and_csrf(self):
        self.client.force_login(self.actor)
        url = reverse('bling_schedules')
        self.assertContains(self.client.get(url), 'Busca automática de notas')
        self.assertEqual(self.client.post(url, {'kind':'SALE','enabled':'on','interval_hours':2,'lookback_days':14}).status_code,302)
        obj=BlingSchedule.objects.get(kind='SALE');self.assertEqual(obj.interval_hours,2)
        self.assertContains(self.client.post(url, {'kind':'SALE','enabled':'on','interval_hours':0,'lookback_days':14}), 'maior ou igual')
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.actor)
        self.assertEqual(strict.post(url, {'kind':'SALE'}).status_code,403)
        operator=User.objects.create_user('operator');self.client.force_login(operator)
        self.assertEqual(self.client.get(url).status_code,403)
        with self.assertRaises(PermissionDenied):configure(actor=operator,kind='SALE',data={})
        self.conn.tokens='';self.conn.save()
        with self.assertRaises(ValidationError):self.config()
