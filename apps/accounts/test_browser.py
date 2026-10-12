import os
from unittest import skipUnless
from pathlib import Path
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from apps.core.models import Company


@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class EmployeeAccessBrowser(StaticLiveServerTestCase):
    def test_master_profile_creation_search_save_and_employee_denial(self):
        from playwright.sync_api import sync_playwright, expect
        master=User.objects.create_superuser('master_settings')
        Company.objects.create(pk=1)
        client=Client();client.force_login(master)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(self.live_server_url+reverse('configuration'))
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/mvet20-settings-desktop.png',full_page=True)
            page.get_by_role('link',name='Funcionários e permissões',exact=False).click()
            page.get_by_role('link',name='Cadastrar funcionário',exact=True).click()
            page.locator('#id_username').fill('employee_browser')
            page.locator('#id_first_name').fill('Funcionário teste')
            page.locator('#id_password1').fill('Synthetic-Employee-Browser-846!')
            page.locator('#id_password2').fill('Synthetic-Employee-Browser-846!')
            page.get_by_role('button',name='Cadastrar e definir acessos').click()
            page.locator('#access-profile').select_option('commercial')
            page.get_by_role('button',name='Aplicar à seleção').click()
            expect(page.locator('#access-summary')).to_contain_text('5 permissões')
            page.get_by_label('Localizar uma permissão',exact=True).fill('custos')
            expect(page.locator('.permission-option:visible')).not_to_have_count(0)
            page.get_by_label('Localizar uma permissão',exact=True).fill('')
            page.screenshot(path='artifacts/mvet20-permissions-desktop.png',full_page=True)
            page.get_by_role('button',name='Salvar acessos',exact=True).click()
            page.get_by_text('Acessos salvos.',exact=False).wait_for()
            page.set_viewport_size({'width':390,'height':844})
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.screenshot(path='artifacts/mvet20-permissions-mobile.png',full_page=True)
            self.assertEqual(errors,[]);browser.close()
        worker=User.objects.get(username='employee_browser')
        self.assertTrue(worker.has_perm('core.confirm_sales'))
        self.assertFalse(worker.has_perm('core.cancel_sales'))
        self.assertFalse(worker.has_perm('core.view_costs'))
        self.assertFalse(worker.has_perm('core.view_finance'))
        client.force_login(worker)
        self.assertEqual(client.get(reverse('configuration')).status_code,403)
        self.assertEqual(client.get(reverse('user_access_list')).status_code,403)
