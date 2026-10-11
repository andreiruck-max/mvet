import os
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from apps.accounts.models import AccessPolicy
from .tests import ReportingFixture


@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ExportBrowser(ReportingFixture,StaticLiveServerTestCase):
    def test_master_changes_permissions_and_both_downloads(self):
        from playwright.sync_api import sync_playwright
        from pathlib import Path
        from decimal import Decimal
        from apps.sales.models import SalesChannel
        self.confirmed()
        other=SalesChannel.objects.create(name='Canal de exemplo')
        self.confirmed(invoice_number='999',channel=other,products_amount=Decimal('300'))
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(accept_downloads=True)
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+reverse('user_access',args=[self.operator.pk]))
            page.get_by_label('Consultar faturamento consolidado (sem margens)',exact=True).check()
            page.get_by_label('Exportar indicadores em Excel e PDF',exact=True).check()
            page.get_by_role('button',name='Salvar acessos',exact=True).click()
            page.get_by_text('Acessos salvos.',exact=False).wait_for()
            page.goto(self.live_server_url+reverse('sales_sheet'))
            self.assertIn('Total da empresa',page.locator('.channel-card').first.inner_text())
            page.get_by_role('button',name='Ocultar valores dos cartões').click()
            self.assertNotIn('R$',page.locator('.report-cards').inner_text())
            page.reload()
            self.assertNotIn('R$',page.locator('.report-cards').inner_text())
            page.get_by_role('button',name='Mostrar valores dos cartões').click()
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/report-cards-privacy.png',full_page=True)
            page.locator('.channel-card').filter(has_text='Canal de exemplo').click()
            self.assertEqual(page.locator('.channel-ledger').count(),1)
            for label,extension in [('Exportar Excel','.xlsx'),('Exportar PDF','.pdf')]:
                with page.expect_download() as info:page.get_by_role('link',name=label+' · todos os canais',exact=True).click()
                download=info.value
                download.save_as('artifacts/sales-organized'+extension)
                self.assertTrue(download.suggested_filename.endswith(extension));self.assertIsNone(download.failure())
            browser.close()
        policy=AccessPolicy.objects.get(user=self.operator)
        self.assertTrue(policy.rules['core.view_dashboard']);self.assertFalse(policy.rules['core.view_margins'])

    def test_revenue_only_no_sensitive_columns_or_downloads(self):
        from playwright.sync_api import sync_playwright
        AccessPolicy.objects.create(user=self.operator,rules={'core.view_dashboard':True})
        client=Client();client.force_login(self.operator)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':390,'height':844})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+reverse('dashboard'))
            page.get_by_role('heading',name='Dashboard gerencial',exact=True).wait_for()
            self.assertEqual(page.get_by_role('link',name='Exportar Excel',exact=True).count(),0)
            self.assertNotIn('CMV',page.locator('main').inner_text())
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            browser.close()

    def test_renegotiated_purchase_and_projected_cash_download(self):
        from datetime import timedelta
        from decimal import Decimal
        from pathlib import Path
        from io import BytesIO
        from zipfile import ZipFile
        from xml.etree import ElementTree as ET
        from playwright.sync_api import sync_playwright
        from apps.finance import services
        from .files import NS
        purchase=self.purchase();title=purchase.installments.first().financial_title
        day=self.today+timedelta(days=5)
        services.schedule_title(actor=self.actor,pk=title.pk,due_date=day,account=self.account,
            notes='Vencimento renegociado',revision=title.revision)
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(accept_downloads=True)
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+reverse('purchase_detail',args=[purchase.pk]))
            page.get_by_text('Original: '+self.today.strftime('%d/%m/%Y'),exact=True).wait_for()
            self.assertIn(day.strftime('%d/%m/%Y'),page.locator('main').inner_text())
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/review-purchase-reschedule.png',full_page=True)
            page.goto(self.live_server_url+reverse('finance')+f'?start={day}&end={day}&mode=projected')
            with page.expect_download() as info:
                page.get_by_role('link',name='Exportar Excel',exact=True).click()
            download=info.value;self.assertIsNone(download.failure())
            with ZipFile(BytesIO(Path(download.path()).read_bytes())) as book:
                root=ET.fromstring(book.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(Decimal(root.find(f'.//{{{NS}}}c[@r="D3"]/{{{NS}}}v').text),Decimal(975))
            page.screenshot(path='artifacts/review-projected-cash.png',full_page=True)
            browser.close()
