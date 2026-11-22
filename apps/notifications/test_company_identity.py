from django.contrib.auth.models import User
from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from apps.core.models import Company
from .models import Notification, NotificationRead, NotificationPreference


class NotificationCompanyMigrationTests(TransactionTestCase):
    def test_history_and_read_preferences_survive(self):
        Company.objects.get_or_create(pk=1)
        user = User.objects.create_user('notification-history')
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [('notifications', '0001_initial')]
        try:
            executor.migrate(before)
            state = executor.loader.project_state(before).apps
            alert = state.get_model('notifications', 'Notification').objects.create(
                kind='DUE', entity_id=123, title='Histórico', description='Sintético',
                severity='WARNING', fingerprint='a' * 64, revision=3)
            state.get_model('notifications', 'NotificationRead').objects.create(
                notification_id=alert.pk, user_id=user.pk, revision=3)
            state.get_model('notifications', 'NotificationPreference').objects.create(
                user_id=user.pk, kind='DUE', enabled=False)
            originals = {}
            for name in ['Notification', 'NotificationRead', 'NotificationPreference']:
                model = state.get_model('notifications', name)
                fields = [f.attname for f in model._meta.concrete_fields]
                originals[name] = (fields, list(model.objects.order_by('pk').values(*fields)))
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            for model in [Notification, NotificationRead, NotificationPreference]:
                fields, rows = originals[model.__name__]
                self.assertEqual(list(model.objects.order_by('pk').values(*fields)), rows)
                self.assertEqual(set(model.objects.values_list('company_id', flat=True)), {1})
            Company.objects.get_or_create(pk=2, defaults={'active': False})
            for model in [Notification, NotificationRead, NotificationPreference]:
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.update(company_id=2)
        finally:
            MigrationExecutor(connection).migrate(latest)
