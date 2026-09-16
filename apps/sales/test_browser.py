"""End-to-end sale entry using only synthetic inventory."""
import os
from pathlib import Path
from decimal import Decimal
from unittest import skipUnless
from uuid import uuid4
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings, Client
from django.contrib.auth.models import User
from apps.core.models import Company
from apps.products.models import Product
from apps.inventory.models import StockLocation
from apps.inventory.services import execute
from .models import SalesChannel, TaxRule, Sale

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class SalesBrowser(StaticLiveServerTestCase):
    def test_create_confirm_cancel_multiline_sale(self):
        from playwright.sync_api import sync_playwright
        company=Company.objects.create(pk=1);actor=User.objects.create_superuser('sales-browser')
        location=StockLocation.objects.create(name='Local de teste');channel=SalesChannel.objects.create(name='Canal de teste')
        rule=TaxRule.objects.create(name='Regra de demonstração',rate=Decimal('5'),starts_on=company.cutover_date,base='REVENUE')
        product=Product.objects.create(sku='DEMO-01',name='Produto de demonstração')
        execute(actor=actor,key=uuid4(),kind='OPENING',date=company.cutover_date,reason='Dados sintéticos',product_id=product.pk,location_id=location.pk,quantity=Decimal('10'),cost=Decimal('5'))
        client=Client();client.force_login(actor);output=Path('artifacts');output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(self.live_server_url+'/vendas/nova/')
            page.get_by_label('Número da NF:',exact=True).fill('9876')
            page.get_by_label('Valor dos produtos (R$):',exact=True).fill('100')
            page.get_by_role('searchbox',name='Produto',exact=True).fill('DEMO-01')
            page.get_by_role('button',name='DEMO-01 · Produto de demonstração',exact=True).click()
            page.get_by_label('Quantidade:',exact=True).fill('2')
            page.get_by_role('button',name='Adicionar produto',exact=True).click()
            page.get_by_role('searchbox',name='Produto',exact=True).nth(1).fill('DEMO-01')
            page.get_by_role('button',name='DEMO-01 · Produto de demonstração',exact=True).click()
            page.get_by_label('Quantidade:',exact=True).nth(1).fill('1')
            page.screenshot(path=str(output/'sales-entry-desktop.png'),full_page=True)
            page.get_by_role('button',name='Salvar e revisar',exact=True).click()
            page.get_by_text('Rascunho salvo. Revise e confirme para baixar o estoque.',exact=True).wait_for()
            page.get_by_role('button',name='Confirmar venda',exact=True).click()
            page.get_by_text('Venda confirmada. Estoque atualizado.',exact=True).wait_for()
            page.get_by_role('heading',name='Margem de contribuição',exact=True).wait_for()
            page.screenshot(path=str(output/'sales-confirmed-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'sales-confirmed-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.locator('summary').click();page.get_by_label('Motivo do cancelamento:',exact=True).fill('Cancelamento de teste')
            page.get_by_role('button',name='Confirmar cancelamento',exact=True).click()
            page.get_by_text('Venda cancelada. Movimentos preservados e estoque reposto, quando aplicável.',exact=True).wait_for()
            self.assertEqual(errors,[]);browser.close()
        product.refresh_from_db();self.assertEqual(product.quantity,10)
        sale=Sale.objects.get(invoice_number='9876');self.assertEqual(sale.status,'CANCELLED');self.assertEqual(sale.cmv,15)
