"""Synthetic purchase tax preview, import and isolated installment cancellation."""
import os
import re
from unittest import skipUnless
from pathlib import Path
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from apps.sales.tests import Fixture
from apps.purchases.models import Supplier, Purchase
from .models import BlingConnection
from .tests import ISSUER
from .test_purchase_import import incoming, SUPPLIER
from . import purchase_services

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PurchaseTaxesBrowser(Fixture,StaticLiveServerTestCase):
    def test_tax_preview_import_and_single_cancel(self):
        from playwright.sync_api import sync_playwright
        supplier=Supplier.objects.create(legal_name='Fornecedor sintético',document=SUPPLIER)
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        row=purchase_services.stage(actor=self.actor,connection=connection,payload=incoming(valorNota='110',
            _xml_discounts={'total':'0','items':['0'],'tax_items':[{'ncm':'85437092','ipi':'10'}]}))
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.live_server_url+f'/integracoes/bling/compras/{row.pk}/')
            page.locator('[name="supplier"]').select_option(str(supplier.pk))
            page.locator('[name="location"]').select_option(str(self.location.pk))
            page.locator('[name="st_by_ncm"]').fill('85437092=20,00')
            page.locator('[name="reviewed"]').check()
            page.locator('[name="taxes_reviewed"]').check()
            # Source parcel is a synthetic R$100; reconcile with the explicit IPI.
            page.locator('[name="installments-0-amount"]').fill('110,00')
            page.get_by_role('button',name='Calcular prévia dos custos',exact=True).click()
            page.locator('#acquisition-preview').wait_for()
            self.assertIn('130,00',page.locator('#acquisition-preview').inner_text())
            page.get_by_role('button',name='Importar rascunho de compra',exact=True).click()
            page.get_by_role('button',name='Confirmar compra',exact=True).click()
            page.get_by_text('Compra confirmada. Parcelas registradas; estoque aguarda recebimento.',exact=True).wait_for()
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/purchase-tax-preview-confirmed.png',full_page=True)
            href=page.get_by_role('link',name=re.compile('Parcela 1 —')).get_attribute('href')
            page.goto(self.live_server_url+href)
            page.get_by_text('Cancelar somente este título / parcela',exact=True).click()
            page.get_by_label('Motivo:',exact=True).fill('Dispensa da parcela sintética')
            page.get_by_role('button',name='Cancelar título',exact=True).click()
            page.get_by_text('Operação financeira confirmada.',exact=True).wait_for()
            self.assertEqual(errors,[])
            browser.close()
        purchase=Purchase.objects.get()
        self.assertEqual(purchase.total,110)
        self.assertEqual(purchase.acquisition_total,130)
        self.assertEqual(purchase.installments.get().status,"CANCELLED")
