import os
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from .tests import ReportingFixture

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ReportingBrowser(ReportingFixture,StaticLiveServerTestCase):
    def test_channel_grid_sticky_totals_collapse_and_dre_origins(self):
        from decimal import Decimal
        from pathlib import Path
        from playwright.sync_api import sync_playwright
        from apps.sales.models import SalesChannel
        for index in range(24):
            self.confirmed(invoice_number=str(500+index),products_amount=Decimal(1) if index==0 else Decimal(100),discount=Decimal(0),shipping_received=Decimal(0))
        other=SalesChannel.objects.create(name='Segundo canal')
        self.confirmed(invoice_number='999',channel=other)
        expense=self.expense()
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+reverse('sales_sheet'))
            self.assertEqual(page.locator('.channel-ledger').count(),2)
            grid=page.locator('.channel-scroll').first
            headers=grid.locator('thead tr').first.locator('th')
            cells=grid.locator('tbody tr').first.locator('td')
            self.assertEqual(headers.count(),cells.count())
            for index in range(headers.count()):
                self.assertAlmostEqual(headers.nth(index).bounding_box()['x'],cells.nth(index).bounding_box()['x'],delta=1)
                self.assertAlmostEqual(headers.nth(index).bounding_box()['width'],cells.nth(index).bounding_box()['width'],delta=1)
            grid.scroll_into_view_if_needed()
            before=grid.locator('thead').bounding_box()['y']
            grid.evaluate('(el)=>{el.scrollTop=500;el.scrollLeft=180}')
            self.assertGreater(grid.evaluate('(el)=>el.scrollTop'),0)
            self.assertAlmostEqual(grid.locator('thead').bounding_box()['y'],before,delta=1)
            self.assertTrue(grid.locator('.channel-totals').is_visible())
            self.assertGreater(page.locator('tbody .result-negative').count(),0)
            self.assertEqual(page.locator('tbody .result-negative').first.evaluate('(el)=>getComputedStyle(el).color'),'rgb(188, 32, 43)')
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/sales-review-sticky.png',full_page=True)
            page.locator('.channel-ledger summary').first.click()
            self.assertFalse(grid.is_visible());self.assertTrue(page.locator('.channel-scroll').nth(1).is_visible())
            page.locator('.channel-ledger summary').first.click()
            page.locator('#theme-toggle').click()
            page.screenshot(path='artifacts/sales-review-dark.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            self.assertEqual(grid.locator('table').evaluate('(el)=>getComputedStyle(el).display'),'table')
            page.screenshot(path='artifacts/sales-review-mobile.png',full_page=True)
            page.set_viewport_size({'width':1440,'height':1050})
            page.goto(self.live_server_url+reverse('dre'))
            page.get_by_role('link',name='(−) Despesas operacionais da empresa',exact=True).click()
            page.get_by_role('heading',name='Lançamentos da DRE',exact=False).wait_for()
            self.assertIn('Serviço mensal',page.locator('main').inner_text())
            page.screenshot(path='artifacts/dre-review-sources.png',full_page=True)
            page.get_by_role('link',name='Abrir origem / modificar',exact=True).click()
            self.assertIn(reverse('expense_detail',args=[expense.pk]),page.url)
            browser.close()

    def test_dashboard_sheets_dre_payables_and_daily_cash(self):
        from playwright.sync_api import sync_playwright
        self.confirmed();self.expense();self.purchase()
        from apps.finance import services as finance
        from decimal import Decimal
        for index in range(1, 6):
            finance.save_account(actor=self.actor,data=dict(name=f'Conta exemplo {index}',kind='BANK',opening_date=self.today,opening_balance=Decimal(index * 1000)))
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.live_server_url+reverse('dashboard'))
            page.get_by_role('heading',name='Dashboard gerencial',exact=True).wait_for()
            self.assertTrue(page.locator('#id_start').input_value())
            self.assertTrue(page.locator('#id_end').input_value())
            from pathlib import Path
            Path('artifacts').mkdir(exist_ok=True)
            self.assertLess(page.locator('.dashboard-channels').bounding_box()['y'],750)
            page.screenshot(path='artifacts/dashboard-desktop.png',full_page=True)
            page.get_by_role('link',name='Conferir vendas e deduções em tabela',exact=False).click()
            page.get_by_role('heading',name='Relatório de vendas',exact=True).wait_for()
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
            page.get_by_role('heading',name='Compras · parcelas a pagar',exact=True).wait_for()
            self.assertLess(page.locator('.payables-sheet tbody tr').first.bounding_box()['y'],850)
            page.get_by_role('columnheader',name='Produtos',exact=True).wait_for()
            page.screenshot(path='artifacts/payables-compact-desktop.png',full_page=True)
            page.locator('.payable-summary > summary').nth(0).click()
            page.locator('.payable-summary > summary').nth(1).click()
            page.screenshot(path='artifacts/payables-totals-desktop.png',full_page=True)
            page.get_by_role('link',name='Pagar / antecipar',exact=True).first.click()
            page.get_by_role('heading',name='Pagar / antecipar parcela',exact=True).wait_for()
            page.get_by_role('link',name='Fluxo diário',exact=True).click()
            page.get_by_label('Período:',exact=True).select_option('month')
            page.get_by_role('button',name='Consultar',exact=True).click()
            import calendar
            self.assertEqual(page.locator('.cash-date').count(),calendar.monthrange(self.today.year,self.today.month)[1])
            self.assertLess(page.locator('.cash-matrix tbody tr').first.bounding_box()['y'],600)
            page.screenshot(path='artifacts/cash-matrix-desktop.png',full_page=True)
            self.assertEqual(page.locator('.cash-page nav[aria-label="Paginação"]').count(),0)
            for name in ['dashboard','sales_sheet','dre','purchase_payables','finance','products','purchases','sales','expenses','financial_titles','notifications','configuration','bling_queue','bling_purchase_queue']:
                page.set_viewport_size({'width':1440,'height':1050})
                page.goto(self.live_server_url+reverse(name))
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),1440,name)
                page.screenshot(path=f'artifacts/layout-{name}-desktop.png',full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390,name)
                self.assertGreater(page.locator('h1').inner_text().__len__(),0)
                page.screenshot(path=f'artifacts/layout-{name}-mobile.png',full_page=True)
            page.locator('#theme-toggle').click()
            self.assertEqual(page.locator('html').get_attribute('data-theme'),'dark')
            self.assertEqual(errors,[]);browser.close()

    def test_sales_filters_apply_without_consult_and_invoice_numeric_order(self):
        from playwright.sync_api import sync_playwright, expect
        for number in ('100','9','10'):self.confirmed(invoice_number=number)
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+reverse('sales_sheet'))
            self.assertEqual(page.locator('.sales-sheet tbody td:nth-child(2) a').all_text_contents(),['NF 9','NF 10','NF 100'])
            with page.expect_navigation():page.locator('#id_sort').select_option('-date')
            self.assertIn('sort=-date',page.url)
            with page.expect_navigation():page.locator('#id_q').fill('100')
            expect(page.locator('.sales-sheet tbody tr')).to_have_count(1)
            self.assertIn('q=100',page.url)
            with page.expect_navigation():page.locator('#id_start').fill(str(self.today))
            self.assertEqual(page.locator('#id_period').input_value(),'')
            with page.expect_navigation():page.locator('#id_status').select_option('DRAFT')
            expect(page.locator('.sales-sheet tbody tr')).to_have_count(0)
            browser.close()

    def test_submenus_channel_cards_and_payable_summaries(self):
        from pathlib import Path
        from playwright.sync_api import sync_playwright, expect
        from apps.sales.models import SalesChannel
        self.purchase();self.confirmed()
        other=SalesChannel.objects.create(name='Novo canal')
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+reverse('sales_sheet'))
            with page.expect_navigation():page.locator('.channel-card').filter(has_text='Novo canal').click()
            self.assertIn('channel='+str(other.pk),page.url)
            expect(page.locator('.channel-ledger')).to_have_count(0)
            page.locator('.nav-submenu[data-menu="purchases"] > summary').click()
            with page.expect_navigation():page.locator('#main-navigation').get_by_role('link',name='Parcelas a pagar',exact=True).click()
            expect(page.locator('.nav-submenu[data-menu="purchases"]')).to_have_attribute('open','')
            page.locator('.payable-summary > summary').nth(0).click()
            page.locator('.payable-summary > summary').nth(1).click()
            expect(page.locator('.payable-summary table').nth(1)).to_contain_text('Valor médio')
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/purchases-summary-desktop.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.screenshot(path='artifacts/purchases-summary-mobile.png',full_page=True)
            browser.close()
