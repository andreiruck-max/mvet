import os
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from .tests import ReportingFixture

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ReportingBrowser(ReportingFixture,StaticLiveServerTestCase):
    def test_dashboard_sheets_dre_payables_and_daily_cash(self):
        from playwright.sync_api import sync_playwright
        self.confirmed();self.expense();self.purchase()
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.live_server_url+reverse('dashboard'))
            page.get_by_role('heading',name='Dashboard gerencial',exact=True).wait_for()
            from pathlib import Path
            Path('artifacts').mkdir(exist_ok=True)
            self.assertLess(page.locator('.dashboard-channels').bounding_box()['y'],750)
            page.screenshot(path='artifacts/dashboard-desktop.png',full_page=True)
            page.get_by_role('link',name='Conferir vendas e deduções em tabela',exact=False).click()
            page.get_by_role('heading',name='Vendas em tabela',exact=True).wait_for()
            self.assertEqual(page.locator('.sales-sheet tbody tr').count(),1)
            page.get_by_role('columnheader',name='CMV histórico',exact=True).wait_for()
            self.assertLess(page.locator('.sales-sheet tbody tr').first.bounding_box()['y'],750)
            self.assertLessEqual(page.locator('.sales-sheet').evaluate('(el)=>el.scrollWidth'),page.locator('.sales-sheet').evaluate('(el)=>el.clientWidth')+1)
            page.get_by_text('Total da empresa',exact=True).wait_for()
            from pathlib import Path
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/sales-compact-desktop.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.screenshot(path='artifacts/sales-compact-mobile.png',full_page=True)
            page.set_viewport_size({'width':1440,'height':1050})
            self.assertIn('start=',page.url)
            page.get_by_role('link',name='DRE',exact=True).click()
            page.get_by_role('heading',name='DRE gerencial por competência',exact=True).wait_for()
            page.get_by_role('cell',name='EBITDA gerencial',exact=True).wait_for()
            page.get_by_role('link',name='Compras a pagar',exact=True).click()
            page.get_by_role('heading',name='Compras a pagar',exact=True).wait_for()
            self.assertLess(page.locator('.payables-sheet tbody tr').first.bounding_box()['y'],850)
            page.get_by_role('columnheader',name='Produtos',exact=True).wait_for()
            page.screenshot(path='artifacts/payables-compact-desktop.png',full_page=True)
            page.get_by_text('Totais por mês',exact=True).click()
            page.get_by_text('Totais por fornecedor',exact=True).click()
            page.screenshot(path='artifacts/payables-totals-desktop.png',full_page=True)
            page.get_by_role('link',name='Marcar como pago',exact=True).first.click()
            page.get_by_role('heading',name='Marcar como pago',exact=True).wait_for()
            page.get_by_role('link',name='Fluxo diário',exact=True).click()
            page.get_by_label('Período:',exact=True).select_option('month')
            page.get_by_role('button',name='Consultar',exact=True).click()
            self.assertEqual(page.locator('.cash-date').count(),14)
            self.assertLess(page.locator('.cash-matrix tbody tr').first.bounding_box()['y'],600)
            page.screenshot(path='artifacts/cash-matrix-desktop.png',full_page=True)
            page.get_by_role('link',name='Próxima',exact=True).first.click()
            self.assertIn('page=2',page.url)
            for name in ['dashboard','sales_sheet','dre','purchase_payables','finance','products','purchases','sales','expenses','financial_titles','notifications','configuration','bling_queue','bling_purchase_queue']:
                page.goto(self.live_server_url+reverse(name));page.set_viewport_size({'width':390,'height':844})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390,name)
                self.assertGreater(page.locator('h1').inner_text().__len__(),0)
                page.screenshot(path=f'artifacts/layout-{name}-mobile.png',full_page=True)
            page.locator('#theme-toggle').click()
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'dark')
            self.assertEqual(errors,[]);browser.close()
