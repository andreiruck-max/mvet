import os
from decimal import Decimal
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from apps.reporting.tests import ReportingFixture
from .services import refresh
from .models import NotificationRead


@skipUnless(os.environ.get('MVET_BROWSER_TESTS') == '1', 'Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class NotificationsBrowser(ReportingFixture, StaticLiveServerTestCase):
    def test_read_preferences_configuration_and_mobile(self):
        from playwright.sync_api import sync_playwright
        self.product.minimum = Decimal('11'); self.product.save(update_fields=['minimum']); refresh()
        client = Client(); client.force_login(self.actor)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={'width': 1440, 'height': 1050}, locale='pt-BR')
            context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value, 'url': self.live_server_url}])
            page = context.new_page(); errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(self.live_server_url+reverse('notifications'))
            page.get_by_role('heading', name='Central de notificações', exact=True).wait_for()
            page.get_by_role('button', name='Marcar como lida', exact=True).click()
            self.assertEqual(page.locator('.notification').count(), 1)
            self.assertEqual(page.get_by_role('button', name='Marcar como lida', exact=True).count(), 0)
            page.get_by_role('link', name='Minhas preferências', exact=True).click()
            page.get_by_label('Estoque mínimo', exact=True).uncheck()
            page.get_by_role('button', name='Salvar preferências', exact=True).click()
            self.assertEqual(page.locator('.notification').count(), 0)
            page.get_by_role('link', name='Configurar alertas', exact=True).click()
            page.get_by_label('Antecedência em dias:', exact=True).fill('5')
            page.get_by_role('button', name='Salvar preferências', exact=True).click()
            page.get_by_text('Configuração salva.', exact=False).wait_for()
            for name in ['notifications', 'notification_preferences', 'notification_configuration']:
                page.goto(self.live_server_url+reverse(name)); page.set_viewport_size({'width': 390, 'height': 844})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), 390, name)
            self.assertEqual(errors, []); browser.close()
        self.assertEqual(NotificationRead.objects.count(), 1)
