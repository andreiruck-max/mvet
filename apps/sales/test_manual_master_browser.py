import os
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from .tests import Fixture
from .models import Sale


@skipUnless(os.environ.get('MVET_BROWSER_TESTS') == '1', 'Browser acceptance enabled in CI')
@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ManualMasterBrowser(Fixture, StaticLiveServerTestCase):
    def test_no_invoice_zero_tax_and_net_adjustment(self):
        from playwright.sync_api import sync_playwright
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context()
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+'/vendas/nova/')
            page.locator('#id_location').select_option(str(self.location.pk))
            page.locator('#id_channel').select_option(str(self.channel.pk))
            page.locator('#id_products_amount').fill('100')
            page.locator('#id_revenue_target').fill('80')
            page.get_by_role('searchbox',name='Produto',exact=True).fill('TEST-1')
            page.get_by_role('button',name='TEST-1 · Produto teste',exact=True).click()
            page.locator('main summary').click()
            page.locator('#id_tax_override').fill('0')
            page.get_by_role('button',name='Salvar e revisar',exact=True).click()
            page.get_by_text('Rascunho salvo. Revise e confirme para baixar o estoque.',exact=True).wait_for()
            page.get_by_role('button',name='Confirmar venda',exact=True).click()
            page.get_by_text('Venda confirmada. Estoque atualizado.',exact=True).wait_for()
            browser.close()
        sale=Sale.objects.get();self.assertEqual(sale.invoice_number,'')
        self.assertEqual(sale.revenue,80);self.assertEqual(sale.tax_amount,0);self.assertEqual(sale.cmv,5)

    def test_cost_correction_preview_and_confirmation(self):
        from decimal import Decimal
        from playwright.sync_api import sync_playwright
        from django.urls import reverse
        sale = self.confirmed()
        item = sale.items.get()
        client = Client(); client.force_login(self.actor)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(); context = browser.new_context()
            context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value, 'url': self.live_server_url}])
            page = context.new_page()
            page.goto(self.live_server_url + reverse('sale_detail', args=[sale.pk]))
            page.get_by_role('link', name='Corrigir CMV', exact=True).click()
            page.locator('#id_cost_' + str(item.pk)).fill('1,50')
            page.locator('#id_reason').fill('Correção do custo unitário conferido')
            page.get_by_role('button', name='Conferir correção', exact=True).click()
            page.get_by_role('heading', name='Confira antes de salvar').wait_for()
            page.get_by_role('button', name='Confirmar correção do CMV', exact=True).click()
            page.get_by_text('CMV corrigido nos resultados. Histórico preservado; estoque atual não foi alterado.', exact=True).wait_for()
            browser.close()
        sale.refresh_from_db()
        self.assertEqual(sale.effective_cmv, Decimal(3))
        self.assertEqual(sale.cmv, Decimal(10))

    def test_customer_and_manual_commission_at_entry(self):
        from decimal import Decimal
        from pathlib import Path
        from apps.commissions.models import Payee,CommissionPlan
        from playwright.sync_api import sync_playwright
        payee=Payee.objects.create(name='Vendedor de demonstração',default_rate=Decimal('5'))
        self.channel.commission_payee=payee;self.channel.save()
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+'/vendas/nova/')
            page.locator('#id_customer_name').fill('Cliente manual demonstrativo')
            page.locator('#id_channel').select_option(str(self.channel.pk))
            page.locator('#id_location').select_option(str(self.location.pk))
            page.locator('#id_products_amount').fill('100')
            page.locator('#id_commission_manual_total').fill('7.50')
            page.get_by_role('searchbox',name='Produto',exact=True).fill('TEST-1')
            page.get_by_role('button',name='TEST-1 · Produto teste',exact=True).click()
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/sale-commission-entry.png',full_page=True)
            page.get_by_role('button',name='Salvar e revisar',exact=True).click()
            page.get_by_role('button',name='Confirmar venda',exact=True).click()
            page.get_by_text('Cliente manual demonstrativo',exact=True).wait_for()
            page.get_by_role('link',name='Controle de comissão',exact=True).click()
            self.assertIn('Cliente manual demonstrativo',page.locator('main').inner_text())
            page.screenshot(path='artifacts/sale-automatic-commission.png',full_page=True)
            browser.close()
        plan=CommissionPlan.objects.get()
        self.assertEqual(plan.payee,payee);self.assertEqual(plan.total,Decimal('7.50'))
        self.assertEqual(plan.customer,'Cliente manual demonstrativo')
