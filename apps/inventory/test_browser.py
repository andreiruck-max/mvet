"""Synthetic-data browser acceptance; enabled by MVET_BROWSER_TESTS=1 in CI."""
import os
from pathlib import Path
from unittest import skipUnless
from decimal import Decimal
from django.test import override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.auth.models import User
from django.test import Client
from apps.core.models import Company
from apps.products.models import Product
from .models import StockLocation
from .services import execute
from uuid import uuid4

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BrowserAcceptance(StaticLiveServerTestCase):
    def test_desktop_mobile_and_manual_stock_flow(self):
        from playwright.sync_api import sync_playwright
        company=Company.objects.create(pk=1)
        actor=User.objects.create_superuser('ui-test-owner')
        p=Product.objects.create(sku='TEST-01',name='Produto de demonstração',minimum=2)
        location=StockLocation.objects.create(name='Local de teste')
        execute(actor=actor,key=uuid4(),kind='OPENING',date=company.cutover_date,reason='Dados sintéticos de teste',product_id=p.pk,location_id=location.pk,quantity=Decimal('10'),cost=Decimal('5'))
        client=Client();client.force_login(actor)
        output=Path('artifacts');output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            context=browser.new_context(viewport={'width':1440,'height':1050})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(self.live_server_url+'/estoque/produtos/')
            page.get_by_role('link',name='Produto de demonstração',exact=True).wait_for()
            page.screenshot(path=str(output/'products-desktop.png'),full_page=True)
            page.get_by_role('link',name='Movimentar estoque',exact=True).click()
            page.get_by_role('searchbox',name='Produto',exact=True).fill('TEST-01')
            page.get_by_role('button',name='TEST-01 · Produto de demonstração',exact=True).click()
            page.get_by_label('Local de origem').select_option(str(location.pk))
            page.get_by_label('Quantidade:',exact=True).fill('2')
            page.get_by_label('Custo unitário (R$):',exact=True).fill('10')
            page.get_by_label('Motivo / documento:',exact=True).fill('Entrada sintética')
            page.screenshot(path=str(output/'operation-desktop.png'),full_page=True)
            page.get_by_role('button',name='Confirmar',exact=True).click()
            page.get_by_text('Movimento confirmado.',exact=True).wait_for()
            page.get_by_role('link',name='Produtos e estoque',exact=True).click()
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'products-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            self.assertEqual(errors,[])
            browser.close()
        p.refresh_from_db()
        self.assertEqual(p.quantity,12)
        self.assertEqual(p.value,70)

    def test_mvet15_switch_depot_search_and_totals(self):
        from playwright.sync_api import sync_playwright
        company = Company.objects.create(pk=1)
        actor = User.objects.create_superuser('ui-depots')
        loja = StockLocation.objects.create(name='Estoque Mercadovet')
        full = StockLocation.objects.create(name='Full Mercado Livre')
        company.default_stock_location = loja; company.save()
        product = Product.objects.create(sku='31', name='Produto de teste por depósito')
        Product.objects.create(sku='1031', name='Outro produto')
        for location, qty, cost in [(loja, '10', '5'), (full, '4', '20')]:
            execute(actor=actor, key=uuid4(), kind='RECEIPT', date=company.cutover_date, reason='Teste sintético', product_id=product.pk, location_id=location.pk, quantity=Decimal(qty), cost=Decimal(cost))
        client = Client(); client.force_login(actor)
        output=Path('artifacts');output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(); context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+'/estoque/produtos/')
            totals=page.get_by_role('region',name='Valores de todo o estoque').inner_text()
            page.get_by_role('navigation',name='Selecionar depósito').get_by_role('link',name='Full Mercado Livre',exact=True).click()
            page.get_by_role('heading',name='Full Mercado Livre',exact=True).wait_for()
            self.assertEqual(page.get_by_role('region',name='Valores de todo o estoque').inner_text(),totals)
            page.get_by_label('SKU ou nome').fill('31');page.get_by_role('button',name='Filtrar',exact=True).click()
            self.assertEqual(page.locator('tbody tr').count(),1)
            row=page.locator('tbody tr').inner_text()
            self.assertIn('4,0000',row);self.assertIn('20,000000',row);self.assertNotIn('1031',row)
            page.screenshot(path=str(output/'mvet15-full-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'mvet15-full-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            browser.close()

    def test_count_filter_currency_and_back_navigation(self):
        from playwright.sync_api import sync_playwright
        company=Company.objects.create(pk=1)
        actor=User.objects.create_superuser('count-ui')
        location=StockLocation.objects.create(name='Estoque Mercadovet')
        StockLocation.objects.create(name='Full Mercado Livre')
        company.default_stock_location=location;company.save()
        product=Product.objects.create(sku='31',name='Produto para contagem')
        Product.objects.create(sku='32',name='Produto zerado')
        execute(actor=actor,key=uuid4(),kind='RECEIPT',date=company.cutover_date,reason='Teste UI',product_id=product.pk,location_id=location.pk,quantity=Decimal('10'),cost=Decimal('500'))
        client=Client();client.force_login(actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.on('dialog',lambda dialog:dialog.accept())
            origin=self.live_server_url+'/estoque/produtos/?location='+str(location.pk)+'&positive=1'
            page.goto(origin)
            self.assertEqual(page.locator('tbody tr').count(),1)
            self.assertIn('R$ 5.000,00',page.get_by_role('region',name='Valores de todo o estoque').inner_text())
            page.get_by_role('link',name='Produto para contagem',exact=True).click()
            page.get_by_role('link',name='Editar cadastro',exact=True).click()
            page.get_by_role('link',name='← Voltar',exact=True).click()
            page.get_by_role('heading',name='Produto para contagem',exact=True).wait_for()
            page.get_by_role('link',name='← Voltar',exact=True).click()
            self.assertEqual(page.url,origin)
            page.get_by_role('link',name='Contar / ajustar',exact=True).click()
            page.get_by_label('Quantidade contada:',exact=True).fill('7')
            page.get_by_label('Motivo / observação da contagem:',exact=True).fill('Conferência visual de teste')
            page.get_by_role('button',name='Confirmar contagem',exact=True).click()
            page.get_by_text('Contagem registrada. Ajuste aplicado ao depósito.',exact=True).wait_for()
            self.assertEqual(page.url,origin)
            self.assertIn('7,0000',page.locator('tbody tr').inner_text())
            output=Path('artifacts');output.mkdir(exist_ok=True)
            page.screenshot(path=str(output/'stock-count-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'stock-count-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.get_by_role('link',name='Produto para contagem',exact=True).click()
            page.get_by_role('button',name='Inativar produto',exact=True).click()
            page.get_by_text('Produto inativado; saldos e histórico preservados.',exact=True).wait_for()
            self.assertEqual(page.url,origin)
            browser.close()
        product.refresh_from_db();self.assertEqual(product.quantity,7);self.assertFalse(product.active)
