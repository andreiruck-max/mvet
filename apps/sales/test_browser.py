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
from .tests import Fixture

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class RecoveryBrowser(Fixture,StaticLiveServerTestCase):
    def test_correct_confirmed_sale_with_cent_typing(self):
        from playwright.sync_api import sync_playwright
        from apps.inventory.models import StockMovement
        from django.urls import reverse
        sale=self.confirmed(fees=Decimal('41.62'));moves=StockMovement.objects.count()
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+reverse('sale_detail',args=[sale.pk]))
            page.get_by_role('link',name='Corrigir valores da venda').click()
            fees=page.get_by_label('Taxas (R$):',exact=True);fees.click();fees.press_sequentially('2081')
            self.assertEqual(fees.input_value(),'20.81')
            shipping=page.get_by_label('Frete pago (R$):',exact=True);shipping.click();shipping.press_sequentially('23500')
            self.assertEqual(shipping.input_value(),'235.00')
            shipping.press('Backspace');self.assertEqual(shipping.input_value(),'23.50')
            page.get_by_label('Motivo da correção:',exact=True).fill('Corrigir taxa e frete')
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/sale-correction-desktop.png',full_page=True)
            page.get_by_role('button',name='Salvar correção').click()
            page.get_by_text('Valores corrigidos. Relatórios atualizados e histórico preservado, sem nova baixa de estoque.',exact=True).wait_for()
            browser.close()
        sale.refresh_from_db();self.assertEqual(sale.fees,Decimal('20.81'));self.assertEqual(sale.shipping_paid,Decimal('23.50'))
        self.assertEqual(StockMovement.objects.count(),moves)

    def test_recover_cancelled_sale_from_details(self):
        from playwright.sync_api import sync_playwright, expect
        from .services import confirm, cancel
        from .models import SaleRecovery
        sale=self.draft(fees=Decimal('41.62'))
        sale=confirm(actor=self.actor,sale_id=sale.pk,revision=sale.revision)
        sale=cancel(actor=self.actor,sale_id=sale.pk,reason='Taxa incorreta')
        client=Client();client.force_login(self.actor)
        output=Path('artifacts');output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
            page.goto(self.live_server_url+f'/vendas/{sale.pk}/')
            page.get_by_role('link',name='Recuperar venda / corrigir taxa',exact=True).click()
            page.get_by_label('Taxas corrigidas (R$):',exact=True).fill('20.81')
            page.get_by_label('Motivo da recuperação:',exact=True).fill('Cancelamento por engano ao corrigir taxa')
            page.screenshot(path=str(output/'sale-recovery-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'sale-recovery-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.get_by_role('button',name='Recuperar venda e corrigir taxa',exact=True).click()
            page.get_by_text('Venda recuperada com taxa corrigida. Estoque e relatórios atualizados; histórico preservado.',exact=True).wait_for()
            expect(page.get_by_role('heading',name='Histórico de recuperações')).to_be_visible()
            self.assertEqual(errors,[]);browser.close()
        sale.refresh_from_db();self.product.refresh_from_db()
        self.assertEqual(sale.status,'CONFIRMED');self.assertEqual(sale.fees,Decimal('20.81'))
        self.assertEqual(sale.cmv,Decimal('10'));self.assertEqual(self.product.quantity,Decimal('8'))
        self.assertEqual(SaleRecovery.objects.count(),1)

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class SalesBrowser(StaticLiveServerTestCase):
    def test_create_confirm_cancel_multiline_sale(self):
        from playwright.sync_api import sync_playwright
        company=Company.objects.create(pk=1);actor=User.objects.create_superuser('sales-browser')
        location=StockLocation.objects.create(name='Local de teste');channel=SalesChannel.objects.create(name='Canal de teste')
        full=StockLocation.objects.create(name='Estoque Full')
        company.default_stock_location=location;company.save(update_fields=['default_stock_location'])
        rule=TaxRule.objects.create(name='Regra de demonstração',rate=Decimal('5'),starts_on=company.cutover_date,base='REVENUE')
        product=Product.objects.create(sku='DEMO-01',name='Produto de demonstração')
        execute(actor=actor,key=uuid4(),kind='OPENING',date=company.cutover_date,reason='Dados sintéticos',product_id=product.pk,location_id=location.pk,quantity=Decimal('10'),cost=Decimal('5'))
        execute(actor=actor,key=uuid4(),kind='TRANSFER',date=company.cutover_date,reason='Transferência sintética',product_id=product.pk,location_id=location.pk,target_location_id=full.pk,quantity=Decimal('4'))
        client=Client();client.force_login(actor);output=Path('artifacts');output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(self.live_server_url+'/vendas/nova/')
            self.assertEqual(page.get_by_label('Estoque da venda:',exact=True).input_value(),str(location.pk))
            page.get_by_label('Estoque da venda:',exact=True).select_option(str(full.pk))
            page.get_by_label('Número da NF:',exact=True).fill('9876')
            page.get_by_label('Valor dos produtos (R$):',exact=True).fill('100')
            page.get_by_role('searchbox',name='Produto',exact=True).fill('DEMO-01')
            page.get_by_role('button',name='DEMO-01 · Produto de demonstração',exact=True).click()
            page.get_by_label('Quantidade:',exact=True).fill('2')
            page.get_by_role('button',name='Adicionar produto',exact=True).click()
            page.get_by_role('searchbox',name='Produto',exact=True).nth(1).fill('DEMO-01')
            page.get_by_role('button',name='DEMO-01 · Produto de demonstração',exact=True).click()
            page.get_by_label('Quantidade:',exact=True).nth(1).fill('1')
            page.locator('summary').click()
            page.get_by_label('Desconto (R$):',exact=True).fill('5')
            page.locator('summary').click()
            page.get_by_role('button',name='Adicionar taxa extra',exact=True).click()
            page.get_by_label('Taxa / descrição:',exact=True).fill('MDR')
            page.get_by_label('Valor (R$):',exact=True).fill('3.50')
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(output/'sales-entry-desktop.png'),full_page=True)
            page.get_by_role('button',name='Salvar e revisar',exact=True).click()
            page.get_by_text('Rascunho salvo. Revise e confirme para baixar o estoque.',exact=True).wait_for()
            page.get_by_role('button',name='Confirmar venda',exact=True).click()
            page.get_by_text('Venda confirmada. Estoque atualizado.',exact=True).wait_for()
            page.get_by_role('heading',name='Margem de contribuição',exact=True).wait_for()
            detail_url=page.url
            page.goto(self.live_server_url+f'/vendas/impostos/{rule.pk}/aliquota/')
            page.get_by_label('Nova alíquota (%):',exact=True).fill('10')
            page.get_by_label('Motivo da alteração:',exact=True).fill('Ajuste de teste')
            page.get_by_role('button',name='Aplicar alíquota e vigência',exact=True).click()
            page.get_by_text('Alíquota registrada. 0 venda(s) recalculada(s).',exact=True).wait_for()
            page.screenshot(path=str(output/'sales-tax-change.png'),full_page=True)
            page.goto(detail_url)
            page.screenshot(path=str(output/'sales-confirmed-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'sales-confirmed-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.locator('summary').click();page.get_by_label('Motivo do cancelamento:',exact=True).fill('Cancelamento de teste')
            page.get_by_role('button',name='Confirmar cancelamento',exact=True).click()
            page.get_by_text('Venda cancelada. Movimentos preservados e estoque reposto, quando aplicável.',exact=True).wait_for()
            self.assertEqual(errors,[]);browser.close()
        product.refresh_from_db();self.assertEqual(product.quantity,10)
        sale=Sale.objects.get(invoice_number='9876');self.assertEqual(sale.status,'CANCELLED');self.assertEqual(sale.cmv,15);self.assertEqual(sale.extra_costs_total,Decimal('3.50'));self.assertEqual(sale.tax_amount,Decimal('4.75'))
        self.assertEqual(product.balances.get(location=full).quantity,4);self.assertEqual(product.balances.get(location=location).quantity,6)
