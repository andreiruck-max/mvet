import os
from unittest import skipUnless
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from apps.core.models import Company


@skipUnless(os.environ.get('MVET_BROWSER_TESTS') == '1', 'Browser acceptance enabled in CI')
@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CompanyRegistryBrowser(StaticLiveServerTestCase):
    def test_master_edits_secondary_identity_and_prepares_grant(self):
        from playwright.sync_api import sync_playwright
        Company.objects.get_or_create(pk=1)
        agro, _ = Company.objects.get_or_create(pk=2, defaults={'name': 'MVet Agro', 'active': False})
        master = User.objects.create_superuser('registry-browser')
        employee = User.objects.create_user('registry-employee')
        client = Client(); client.force_login(master)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context()
            context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value, 'url': self.live_server_url}])
            page = context.new_page()
            page.goto(self.live_server_url + '/empresas/2/')
            page.get_by_label('Nome fantasia').fill('MVET AGRO COMERCIAL')
            page.get_by_role('button', name='Salvar cadastro', exact=True).click()
            page.get_by_text('Cadastro salvo.', exact=False).wait_for()
            agro.refresh_from_db()
            self.assertFalse(agro.active)
            self.assertEqual(agro.trade_name, 'MVET AGRO COMERCIAL')
            page.goto(self.live_server_url + f'/usuarios/{employee.pk}/empresas/2/')
            page.get_by_label('Vínculo ativo', exact=True).check()
            page.get_by_role('button', name='Salvar vínculo empresarial').click()
            page.get_by_text('Vínculo empresarial salvo', exact=False).wait_for()
            browser.close()
