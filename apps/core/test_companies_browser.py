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
            page.goto(self.live_server_url + f'/usuarios/{employee.pk}/empresas/2/')
            page.locator('#id_active').check()
            self.assertTrue(page.locator('#id_active').is_checked())
            page.get_by_role('button', name='Salvar vínculo empresarial').click()
            page.get_by_text('Vínculo empresarial salvo', exact=False).wait_for()
            from pathlib import Path
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/company-access-foundation.png', full_page=True)
            browser.close()
        agro.refresh_from_db()
        self.assertFalse(agro.active)
        self.assertEqual(agro.trade_name, 'MVET AGRO COMERCIAL')
        from apps.accounts.models import UserCompanyAccess
        grant = UserCompanyAccess.objects.get(user=employee, company=agro)
        self.assertTrue(grant.active)
        self.assertEqual(grant.rules, {})

    @override_settings(COMPANY_CONTEXT_ENABLED=True)
    def test_group_context_blocks_legacy_dashboard(self):
        from playwright.sync_api import sync_playwright
        from django.urls import reverse
        Company.objects.get_or_create(pk=1)
        actor=User.objects.create_superuser('scope-browser')
        client=Client();client.force_login(actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            context=browser.new_context()
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page()
            page.goto(self.live_server_url+reverse('company_context'))
            self.assertTrue(page.get_by_role('link',name='Contexto: Mercadovet · Trocar empresa',exact=True).is_visible())
            page.locator('#company-scope').select_option('group')
            page.get_by_role('button',name='Selecionar contexto',exact=True).click()
            page.wait_for_load_state()
            response=page.goto(self.live_server_url+reverse('dashboard'))
            self.assertEqual(response.status,403)
            page.goto(self.live_server_url+reverse('company_context'))
            page.locator('#company-scope').select_option('1')
            page.get_by_role('button',name='Selecionar contexto',exact=True).click()
            page.get_by_role('link',name='Abrir Mercadovet',exact=True).wait_for()
            browser.close()

    @override_settings(COMPANY_CONTEXT_ENABLED=True)
    def test_master_prepares_tax_rate_for_agro_without_changing_primary(self):
        from django.urls import reverse
        from django.utils import timezone
        from playwright.sync_api import sync_playwright
        from apps.sales.models import TaxRule
        from apps.sales.taxes import effective_terms
        today = timezone.localdate()
        Company.objects.get_or_create(pk=1)
        agro, _ = Company.objects.get_or_create(pk=2, defaults={'active':False,'name':'Agro de teste'})
        primary = TaxRule.objects.create(company_id=1, name='Vendas padrão',starts_on=today,rate=8,base='REVENUE')
        actor = User.objects.create_superuser('tax-setup-browser')
        client=Client(); client.force_login(actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            ctx=browser.new_context()
            ctx.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=ctx.new_page()
            page.goto(self.live_server_url + reverse('company_registry'))
            page.locator(f'a[href="{reverse("company_tax_rules",args=[agro.pk])}"]').click()
            page.locator('#id_name').fill('Vendas padrão')
            page.locator('#id_rate').fill('4')
            page.locator('#id_starts_on').fill(today.isoformat())
            page.locator('#id_base').select_option('PRODUCTS')
            page.get_by_role('button',name='Salvar',exact=True).click()
            page.get_by_role('link',name='Alíquota e vigência').click()
            page.locator('#id_rate').fill('6')
            page.locator('#id_reason').fill('Nova vigência da Agro')
            page.get_by_role('button',name='Aplicar alíquota e vigência').click()
            page.get_by_text('Alíquota registrada.',exact=True).wait_for()
            page.get_by_role('link',name='Regras tributárias',exact=True).click()
            self.assertIn('6%',page.locator('tbody').inner_text())
            browser.close()
        self.assertEqual(effective_terms(primary,today)[0],8)
        self.assertFalse(Company.objects.get(pk=agro.pk).active)
