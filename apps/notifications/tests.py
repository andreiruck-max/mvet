from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal as D
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, close_old_connections, connections
from django.test import TestCase, TransactionTestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.reporting.tests import ReportingFixture
from apps.core.models import AuditLog
from apps.sales import services as sales
from . import services, selectors
from .models import AlertConfiguration, BackupEvidence, Notification, NotificationRead


class NotificationTests(ReportingFixture, TestCase):
    def stock(self):
        self.product.minimum = D('11')
        self.product.save(update_fields=['minimum'])

    def test_idempotence_and_per_user_read(self):
        self.stock(); services.refresh(); services.refresh()
        n = Notification.objects.get(kind='STOCK')
        self.assertEqual(n.revision, 1)
        services.mark_read(actor=self.operator, pk=n.pk, revision=1)
        services.mark_read(actor=self.operator, pk=n.pk, revision=1)
        self.assertEqual(NotificationRead.objects.count(), 1)
        self.assertTrue(selectors.visible(self.operator).get().is_read)
        self.assertFalse(selectors.visible(self.actor).get().is_read)
        services.refresh()
        self.assertTrue(selectors.visible(self.operator).get().is_read)

    def test_resolve_and_reactivate_reset_read(self):
        self.stock(); services.refresh(); n = Notification.objects.get()
        services.mark_read(actor=self.operator, pk=n.pk, revision=n.revision)
        self.receive(self.product, D('5'), D('5')); services.refresh()
        n.refresh_from_db(); self.assertFalse(n.active); self.assertIsNotNone(n.resolved_at)
        self.product.refresh_from_db(); self.product.minimum = D('20'); self.product.save(update_fields=['minimum'])
        services.refresh(); n.refresh_from_db()
        self.assertTrue(n.active); self.assertEqual(n.revision, 2)
        self.assertFalse(selectors.visible(self.operator).get().is_read)

    def test_zero_threshold_and_virtual_kits_do_not_alert(self):
        self.product.quantity = D('0'); self.product.save(update_fields=['quantity'])
        services.refresh(); self.assertFalse(Notification.objects.exists())
        self.product.kind = 'KIT'; self.product.minimum = D('10'); self.product.save()
        services.refresh(); self.assertFalse(Notification.objects.exists())

    def test_due_escalation_payment_and_cancellation(self):
        title = self.title(due_date=self.today+timedelta(days=1))
        services.refresh(); n = Notification.objects.get(kind='DUE'); self.assertEqual(n.severity, 'INFO')
        title.due_date = self.today; title.save(update_fields=['due_date']); services.refresh()
        n.refresh_from_db(); self.assertEqual(n.severity, 'WARNING')
        title.due_date = self.today-timedelta(days=1); title.save(update_fields=['due_date']); services.refresh()
        n.refresh_from_db(); self.assertEqual(n.severity, 'CRITICAL'); self.assertEqual(n.revision, 3)
        self.pay(title); services.refresh(); n.refresh_from_db(); self.assertFalse(n.active)
        cancelled = self.title()
        cancelled.status = 'CANCELLED'; cancelled.save(update_fields=['status'])
        services.refresh()
        self.assertFalse(Notification.objects.filter(kind='DUE', entity_id=cancelled.pk).exists())

    def test_negative_margin_and_cancelled_sale(self):
        sale = self.confirmed(products_amount=D('15'), discount=D('0'))
        services.refresh(); n = Notification.objects.get(kind='MARGIN')
        self.assertEqual(n.severity, 'CRITICAL')
        self.assertNotIn('MARGIN', selectors.visible(self.operator).values_list('kind', flat=True))
        sales.cancel(actor=self.actor, sale_id=sale.pk, reason='Teste de cancelamento')
        services.refresh(); n.refresh_from_db(); self.assertFalse(n.active)

    def test_retroactive_tax_changes_warning_without_changing_cmv(self):
        from apps.sales.taxes import change_rate
        sale = self.confirmed(products_amount=D('50'))
        services.refresh()
        self.assertFalse(Notification.objects.filter(kind='MARGIN').exists())
        change_rate(actor=self.actor, rule_id=self.rule.pk, rate=D('40'),
            effective_from=self.today-timedelta(days=1), base='REVENUE',
            reason='Correção retroativa de teste', revision=0)
        services.refresh(); sale.refresh_from_db()
        self.assertEqual(sale.cmv, D('10'))
        self.assertEqual(Notification.objects.get(kind='MARGIN').severity, 'WARNING')

    def test_preferences_global_disable_and_auditing(self):
        self.stock(); services.refresh()
        services.preferences(actor=self.operator, enabled=[])
        self.assertFalse(selectors.visible(self.operator).exists())
        self.assertTrue(selectors.visible(self.actor).exists())
        services.preferences(actor=self.operator, enabled=['STOCK'])
        self.assertTrue(selectors.visible(self.operator).exists())
        services.configure(actor=self.actor, data=dict(stock=False, margin=True, due=True, due_days=3, backup=False, backup_hours=36))
        self.assertFalse(selectors.visible(self.actor).exists())
        self.assertTrue(AuditLog.objects.filter(actor=self.actor, operation='notification_configuration').exists())

    def test_no_financial_leak_html_api_read_or_revocation(self):
        self.stock(); self.title(); self.confirmed(products_amount=D('15'), discount=D('0')); services.refresh()
        financial = Notification.objects.filter(kind='DUE').first()
        self.client.force_login(self.operator)
        response = self.client.get(reverse('notifications_api')).json()
        self.assertEqual([r['kind'] for r in response['results']], ['STOCK'])
        self.assertNotContains(self.client.get(reverse('notifications')), 'Título sintético')
        self.assertEqual(self.client.post(reverse('notification_read', args=[financial.pk]), {'revision': 1}).status_code, 404)
        for name in ['notification_configuration', 'notification_refresh']:
            self.assertEqual(self.client.post(reverse(name)).status_code, 403)
        self.operator.user_permissions.clear()
        self.assertEqual(self.client.get(reverse('notifications_api')).json()['count'], 0)

    def test_finance_and_cost_permissions_are_independent(self):
        self.stock(); self.title(); self.confirmed(products_amount=D('15'), discount=D('0')); services.refresh()
        user = User.objects.create_user('finance-only')
        user.user_permissions.add(Permission.objects.get(codename='operate_finance'))
        self.assertEqual(set(selectors.visible(user).values_list('kind', flat=True)), {'DUE'})
        for n in selectors.visible(self.actor):
            self.client.force_login(self.actor)
            self.assertEqual(self.client.get(selectors.destination(n)).status_code, 200)

    def test_csrf_method_pagination_and_stale_read(self):
        self.stock(); services.refresh(); n = Notification.objects.get()
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse('notification_read', args=[n.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse('notification_read', args=[n.pk]), {'revision': 999}).status_code, 404)
        csrf = Client(enforce_csrf_checks=True); csrf.force_login(self.actor)
        self.assertEqual(csrf.post(reverse('notification_refresh')).status_code, 403)
        # PostgreSQL sequences are not rolled back between TestCase fixtures.
        # Use a range relative to this fixture, never fixed production-like IDs.
        for pk in range(n.entity_id + 1, n.entity_id + 36):
            Notification.objects.create(kind='STOCK', entity_id=pk, title='Teste', description='Teste', severity='WARNING', fingerprint='x')
        data = self.client.get(reverse('notifications_api')).json()
        self.assertEqual(len(data['results']), 30); self.assertEqual(data['count'], 36)
        self.assertEqual(self.client.get(reverse('notifications'), {'page': 2}).status_code, 200)

    def test_generator_failure_does_not_undo_sale_or_previous_alerts(self):
        self.stock(); services.refresh(); sale = self.confirmed()
        with patch('apps.notifications.services.conditions', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError): services.refresh()
        sale.refresh_from_db(); self.assertEqual(sale.status, 'CONFIRMED')
        self.assertEqual(Notification.objects.filter(active=True).count(), 1)

    def test_backup_requires_evidence_and_explicit_monitoring(self):
        services.refresh(); self.assertFalse(Notification.objects.filter(kind='BACKUP').exists())
        data = dict(stock=True, margin=True, due=True, due_days=3, backup=True, backup_hours=36)
        services.configure(actor=self.actor, data=data); services.refresh()
        self.assertFalse(Notification.objects.filter(kind='BACKUP').exists())
        AlertConfiguration.objects.update(backup_started_at=timezone.now()-timedelta(hours=37))
        services.refresh(); self.assertTrue(Notification.objects.get(kind='BACKUP').active)
        with self.assertRaises(ValidationError): services.record_backup(success=True)
        call_command('record_backup', 'success', size=150, sha256='a'*64)
        services.refresh(); self.assertFalse(Notification.objects.get(kind='BACKUP').active)
        call_command('record_backup', 'failure'); services.refresh()
        n = Notification.objects.get(kind='BACKUP'); self.assertTrue(n.active); self.assertIn('Falha', n.title)
        services.record_backup(success=True, size_bytes=200, sha256='b'*64)
        services.refresh(); self.assertFalse(Notification.objects.get(kind='BACKUP').active)
        with patch('apps.notifications.services.timezone.now', return_value=timezone.now()+timedelta(hours=38)):
            services.refresh()
        n = Notification.objects.get(kind='BACKUP')
        self.assertTrue(n.active); self.assertIn('sem confirmação', n.title)


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL advisory locks')
class NotificationConcurrencyTests(TransactionTestCase):
    def test_concurrent_refresh_does_not_duplicate(self):
        from apps.products.models import Product
        Product.objects.create(sku='CONCURRENT', name='Teste', minimum=D('1'))
        def run():
            close_old_connections()
            try:
                return services.refresh()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(lambda _: run(), range(2))), [1, 1])
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.get().revision, 1)
