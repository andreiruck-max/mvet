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
            page.get_by_label('Quantidade',exact=True).fill('2')
            page.get_by_label('Custo unitário (R$)',exact=True).fill('10')
            page.get_by_label('Motivo / documento',exact=True).fill('Entrada sintética')
            page.screenshot(path=str(output/'operation-desktop.png'),full_page=True)
            page.get_by_role('button',name='Confirmar',exact=True).click()
            page.get_by_text('Movimento confirmado.',exact=True).wait_for()
            p.refresh_from_db();self.assertEqual(p.quantity,12);self.assertEqual(p.value,70)
            page.get_by_role('link',name='Produtos e estoque',exact=True).click()
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'products-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            self.assertEqual(errors,[])
            browser.close()
