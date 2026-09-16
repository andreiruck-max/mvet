"""Synthetic end-to-end purchase, receipt and warehouse transfer."""
import os
from pathlib import Path
from decimal import Decimal
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings, Client
from django.contrib.auth.models import User
from apps.core.models import Company
from apps.products.models import Product
from apps.inventory.models import StockLocation
from .models import Purchase, Supplier

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PurchasesBrowser(StaticLiveServerTestCase):
    def test_supplier_purchase_receipt_and_transfer(self):
        from playwright.sync_api import sync_playwright
        physical=StockLocation.objects.create(name='Estoque Mercadovet');full=StockLocation.objects.create(name='Estoque Full')
        Company.objects.create(pk=1,default_stock_location=physical)
        actor=User.objects.create_superuser('purchases-browser')
        first=Product.objects.create(sku='PUR-01',name='Primeiro produto de demonstração')
        second=Product.objects.create(sku='PUR-02',name='Segundo produto de demonstração')
        client=Client();client.force_login(actor);output=Path('artifacts');output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(self.live_server_url+'/compras/fornecedores/novo/')
            page.get_by_label('Razão social / nome:',exact=True).fill('Fornecedor de demonstração')
            page.get_by_role('button',name='Salvar fornecedor',exact=True).click()
            page.get_by_role('heading',name='Fornecedor de demonstração',exact=True).wait_for()
            page.goto(self.live_server_url+'/compras/nova/')
            page.get_by_label('Fornecedor:',exact=True).select_option(label='Fornecedor de demonstração')
            page.get_by_label('NF / documento:',exact=True).fill('DEMO-987')
            page.get_by_label('Desconto (R$):',exact=True).fill('1')
            page.get_by_label('Frete de aquisição (R$):',exact=True).fill('3')
            page.get_by_role('searchbox',name='Produto',exact=True).fill('PUR-01')
            page.get_by_role('button',name='PUR-01 · Primeiro produto de demonstração',exact=True).click()
            page.get_by_label('Quantidade:',exact=True).fill('2')
            page.get_by_label('Preço unitário (R$):',exact=True).fill('10')
            page.get_by_role('button',name='Adicionar produto',exact=True).click()
            page.get_by_role('searchbox',name='Produto',exact=True).nth(1).fill('PUR-02')
            page.get_by_role('button',name='PUR-02 · Segundo produto de demonstração',exact=True).click()
            page.get_by_label('Preço unitário (R$):',exact=True).nth(1).fill('20')
            page.get_by_text('Total previsto da compra: R$ 42,00. Confira o rateio ao salvar.',exact=True).wait_for()
            page.get_by_role('button',name='Adicionar parcela',exact=True).click()
            page.get_by_label('Valor da parcela (R$):',exact=True).fill('21')
            page.get_by_role('button',name='Adicionar parcela',exact=True).click()
            self.assertEqual(page.get_by_label('Valor da parcela (R$):',exact=True).nth(1).input_value(),'21.00')
            page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(output/'purchase-entry-desktop.png'),full_page=True)
            page.get_by_role('button',name='Salvar e revisar compra',exact=True).click()
            page.get_by_text('Rascunho salvo. Confira o total, o rateio e as parcelas.',exact=True).wait_for()
            page.get_by_role('button',name='Confirmar compra',exact=True).click()
            page.get_by_text('Compra confirmada. Parcelas registradas; estoque aguarda recebimento.',exact=True).wait_for()
            page.get_by_role('button',name='Confirmar recebimento',exact=True).click()
            page.get_by_text('Compra recebida. Estoque e custo médio atualizados.',exact=True).wait_for()
            page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(output/'purchase-received-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'purchase-received-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.get_by_role('link',name='Transferir produtos para outro estoque',exact=True).click()
            page.get_by_label('Operação:',exact=True).select_option('TRANSFER')
            page.get_by_role('searchbox',name='Produto',exact=True).fill('PUR-01')
            page.get_by_role('button',name='PUR-01 · Primeiro produto de demonstração',exact=True).click()
            page.get_by_label('Local de origem:',exact=True).select_option(str(physical.pk))
            page.get_by_label('Local de destino:',exact=True).select_option(str(full.pk))
            page.get_by_label('Quantidade:',exact=True).fill('1')
            page.get_by_label('Motivo / documento:',exact=True).fill('Reposição do Full')
            page.get_by_role('button',name='Confirmar',exact=True).click()
            page.get_by_text('Movimento confirmado.',exact=True).wait_for()
            self.assertEqual(errors,[]);browser.close()
        purchase=Purchase.objects.get(document='DEMO-987');self.assertEqual(purchase.status,'RECEIVED');self.assertEqual(purchase.total,42);self.assertEqual(purchase.installments.count(),2)
        first.refresh_from_db();self.assertEqual(first.quantity,2);self.assertEqual(first.value,21);self.assertEqual(first.average_cost,Decimal('10.5'))
        self.assertEqual(first.balances.get(location=physical).quantity,1);self.assertEqual(first.balances.get(location=full).quantity,1)
