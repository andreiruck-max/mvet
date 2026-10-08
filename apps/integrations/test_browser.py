import os
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from apps.sales.tests import Fixture
from apps.sales.models import Sale
from .models import BlingConnection
from .services import stage
from .tests import payload, ISSUER


@skipUnless(os.environ.get('MVET_BROWSER_TESTS') == '1', 'Browser acceptance enabled in CI')
@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BlingBrowser(Fixture, StaticLiveServerTestCase):
    def test_calendar_series_customer_defaults_and_negative_sale(self):
        from pathlib import Path
        from playwright.sync_api import sync_playwright
        from .models import InvoiceImport
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        data=payload(contato={'nome':'Cliente demonstrativo'})
        data['itens'][0]['quantidade']='12'
        row=stage(actor=self.actor,connection=connection,payload=data)
        InvoiceImport.objects.create(connection=connection,external_id='2000',series='2',number='12',fingerprint='synthetic')
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.live_server_url+'/integracoes/bling/')
            page.evaluate('''() => { window.pickerCalls=0; const native=HTMLInputElement.prototype.showPicker;
                HTMLInputElement.prototype.showPicker=function(){window.pickerCalls++;return native.call(this);}; }''')
            page.locator('#id_start').click(position={'x':25,'y':15})
            self.assertGreater(page.evaluate('window.pickerCalls'),0)
            page.keyboard.press('Escape')
            page.get_by_label('Série',exact=True).select_option('1')
            page.get_by_role('button',name='Filtrar',exact=True).click()
            self.assertEqual(page.get_by_role('link',name='12 / 2',exact=True).count(),0)
            self.assertTrue(page.get_by_text('Cliente demonstrativo',exact=True).is_visible())
            captures=Path('artifacts');captures.mkdir(exist_ok=True)
            page.screenshot(path=str(captures/'review-package-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            page.screenshot(path=str(captures/'review-package-mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.get_by_role('link',name='123 / 1',exact=True).click()
            self.assertEqual(page.locator('#id_tax_rule').input_value(),str(self.rule.pk))
            page.locator('#id_channel').select_option(str(self.channel.pk))
            page.locator('#id_location').select_option(str(self.location.pk))
            page.get_by_role('button',name='Conferir e confirmar venda',exact=True).click()
            page.get_by_text('Venda confirmada no MVet. Nenhuma alteração foi enviada ao Bling.',exact=True).wait_for()
            self.assertEqual(errors,[]);browser.close()
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,-2)
        self.assertEqual(Sale.objects.get(invoice_number='123').cmv,60)

    def test_review_alias_deductions_and_local_confirmation(self):
        from playwright.sync_api import sync_playwright
        connection = BlingConnection.objects.create(pk=1, issuer=ISSUER)
        data = payload(); data.pop('finalidade'); data['tipoNota'] = ''; data['itens'][0]['codigo'] = 'EXT-DEMO'
        row = stage(actor=self.actor, connection=connection, payload=data)
        client = Client(); client.force_login(self.actor)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(viewport={'width': 1440, 'height': 1050})
            context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value, 'url': self.live_server_url}])
            page = context.new_page(); errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(self.live_server_url + '/integracoes/bling/')
            link = page.get_by_role('link', name='123 / 1', exact=True)
            self.assertTrue(page.get_by_role('link', name='Relatório de vendas', exact=True).is_visible())
            from pathlib import Path
            captures = Path('artifacts'); captures.mkdir(exist_ok=True)
            page.screenshot(path=str(captures / 'bling-compact-desktop.png'), full_page=True)
            print('BLING_LAYOUT', page.locator('.bling-page').evaluate('(el) => Array.from(el.children).map(c => [c.tagName, c.className, c.getBoundingClientRect().y, c.getBoundingClientRect().height])'))
            self.assertLess(link.bounding_box()['y'], 700)
            link.click()
            self.assertEqual(page.locator('#id_discount').input_value(), '0,00')
            self.assertFalse(page.locator('#id_tax_override').is_visible())
            self.assertFalse(page.locator('#id_tax_reason').is_visible())
            page.screenshot(path=str(captures / 'bling-review-desktop.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            page.screenshot(path=str(captures / 'bling-review-mobile.png'), full_page=True)
            page.set_viewport_size({'width': 1440, 'height': 1050})
            page.get_by_text('Vínculo pendente', exact=True).wait_for()
            page.locator('summary').click()
            page.get_by_label('Item da nota:', exact=True).select_option('EXT-DEMO')
            self.assertEqual(page.locator('#id_alias-unit').count(), 0)
            page.get_by_role('searchbox', name='Produto', exact=True).fill('TEST-1')
            page.get_by_role('button', name='TEST-1 · Produto teste', exact=True).click()
            page.get_by_role('button', name='Salvar vínculo', exact=True).click()
            page.get_by_text('Código vinculado. Confira os produtos antes de confirmar a venda.', exact=True).wait_for()
            page.locator('#id_channel').select_option(str(self.channel.pk))
            page.locator('#id_location').select_option(str(self.location.pk))
            page.locator('#id_tax_rule').select_option(str(self.rule.pk))
            for field in ['discount', 'shipping_paid', 'fees', 'difal', 'commission', 'other_costs']:
                page.locator('#id_' + field).fill('0')
            page.get_by_role('button', name='Adicionar taxa extra', exact=True).click()
            page.get_by_label('Taxa / descrição:', exact=True).fill('MDR')
            page.get_by_label('Valor (R$):', exact=True).click()
            page.get_by_label('Valor (R$):', exact=True).press_sequentially('200')
            self.assertEqual(page.locator('#id_reviewed').count(), 0)
            self.assertEqual(page.locator('#id_purpose_reviewed').count(), 0)
            page.get_by_role('button', name='Conferir e confirmar venda', exact=True).click()
            page.get_by_text('Venda confirmada no MVet. Nenhuma alteração foi enviada ao Bling.', exact=True).wait_for()
            page.get_by_role('heading', name='Venda MVet: Confirmada', exact=True).wait_for()
            self.assertEqual(errors, [])
            browser.close()
        sale = Sale.objects.get(invoice_number='123')
        self.assertEqual(sale.cmv, 10); self.assertEqual(sale.extra_costs_total, 2)
        self.product.refresh_from_db(); self.assertEqual(self.product.quantity, 8)

    def test_period_query_fetches_sixty_notes_with_one_click(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from playwright.sync_api import sync_playwright
        from django.utils import timezone
        pages = []
        def batch(**kwargs):
            number = kwargs['page']; pages.append(number)
            return SimpleNamespace(page=number, processed=5 if number <= 12 else 0,
                errors=1 if number == 2 else 0, has_more=number <= 12, message='')
        client = Client(); client.force_login(self.actor)
        with patch('apps.integrations.views.bling.sync_page', side_effect=batch), sync_playwright() as pw:
            browser = pw.chromium.launch(); context = browser.new_context()
            context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value, 'url': self.live_server_url}])
            page = context.new_page(); page.goto(self.live_server_url + '/integracoes/bling/')
            page.locator('#id_start').fill(str(timezone.localdate()))
            page.locator('#id_end').fill(str(timezone.localdate()))
            page.locator('#id_source_status').select_option('5')
            self.assertFalse(page.locator('#id_page').is_visible())
            page.get_by_role('button', name='Buscar notas do período', exact=True).click()
            page.get_by_text('Busca concluída. 60 notas consultadas; 1 pendências. Nenhuma venda foi confirmada.', exact=True).wait_for()
            self.assertEqual(pages, list(range(1, 14)))
            self.assertTrue(page.get_by_role('link', name='Ver notas consultadas e pendências').is_visible())
            browser.close()
        self.assertFalse(Sale.objects.exists())

    def test_period_query_pause_and_error_resume_same_page(self):
        import json
        from playwright.sync_api import sync_playwright
        from django.utils import timezone
        pages = []
        client = Client(); client.force_login(self.actor)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(); context = browser.new_context()
            context.add_cookies([{'name': 'sessionid', 'value': client.cookies['sessionid'].value, 'url': self.live_server_url}])
            page = context.new_page()
            def respond(route):
                # Multipart body contains the hidden page value.
                body = route.request.post_data
                number = int(body.split('name="page"\r\n\r\n')[1].split('\r\n')[0])
                pages.append(number)
                if len(pages) == 1:
                    page.locator('#bling-stop').click()
                    batch = dict(page=1, processed=5, errors=0, has_more=True, blocked=False, next_page=2, message='')
                elif len(pages) == 2:
                    batch = dict(page=2, processed=1, errors=1, has_more=True, blocked=True, next_page=2, message='Limite atingido')
                else:
                    batch = dict(page=2, processed=3, errors=0, has_more=False, blocked=False, next_page=None, message='')
                route.fulfill(status=200, content_type='application/json', body=json.dumps(batch))
            page.route('**/integracoes/bling/consultar/', respond)
            page.goto(self.live_server_url + '/integracoes/bling/')
            page.locator('#id_start').fill(str(timezone.localdate()))
            page.locator('#id_end').fill(str(timezone.localdate()))
            page.locator('#id_source_status').select_option('5')
            page.locator('#bling-start').click()
            page.get_by_text('Busca interrompida. 5 notas consultadas; 0 pendências. Nenhuma venda foi confirmada.', exact=True).wait_for()
            self.assertEqual(pages, [1])
            page.get_by_role('button', name='Retomar busca', exact=True).click()
            page.get_by_text('Limite atingido', exact=False).wait_for()
            page.get_by_role('button', name='Retomar busca', exact=True).click()
            page.get_by_text('Busca concluída. 8 notas consultadas; 0 pendências. Nenhuma venda foi confirmada.', exact=True).wait_for()
            self.assertEqual(pages, [1, 2, 2])
            browser.close()

    def test_purchase_draft_import_and_no_side_effect_before_confirmation(self):
        from playwright.sync_api import sync_playwright
        from django.urls import reverse
        from apps.purchases.models import Supplier, Purchase
        from apps.finance.models import FinancialTitle
        from .test_purchase_import import incoming, SUPPLIER
        from .purchase_services import stage as stage_purchase
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        Supplier.objects.create(legal_name='Fornecedor sintético',document=SUPPLIER)
        invoice=stage_purchase(actor=self.actor,connection=connection,payload=incoming())
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page()
            page.goto(self.live_server_url+reverse('purchases'))
            page.get_by_role('link',name='Importar notas do Bling',exact=True).click()
            page.get_by_role('link',name='123 / 1',exact=True).click()
            page.get_by_role('button',name='Rejeitar nota',exact=True).click()
            page.wait_for_url('**/compras/')
            self.assertEqual(page.get_by_role('link',name='123 / 1',exact=True).count(),0)
            page.locator('#status').select_option('rejected')
            page.get_by_role('button',name='Filtrar',exact=True).click()
            page.get_by_role('link',name='123 / 1',exact=True).click()
            page.get_by_role('button',name='Reabrir nota',exact=True).click()
            page.locator('#id_location').select_option(str(self.location.pk))
            self.assertEqual(page.locator('#id_products-0-product').input_value(),str(self.product.pk))
            page.locator('#id_reviewed').check()
            page.get_by_role('button',name='Importar rascunho de compra',exact=True).click()
            page.wait_for_url('**/compras/*/')
            browser.close()
        self.assertEqual(Purchase.objects.get().status,'DRAFT')
        self.assertFalse(FinancialTitle.objects.exists())
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,10)

    def test_bulk_ignore_and_reopen_selected_invoices(self):
        from playwright.sync_api import sync_playwright
        from django.urls import reverse
        from .models import InvoiceImport
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        invoice=stage(actor=self.actor,connection=connection,payload=payload())
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+reverse('bling_queue'))
            page.get_by_label('Selecionar página',exact=True).check()
            page.get_by_role('button',name='Ignorar / modificar em massa',exact=True).click()
            page.get_by_role('button',name='Revisar alterações',exact=True).click()
            from pathlib import Path
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/bling-bulk-preview.png',full_page=True)
            page.get_by_role('button',name='Aplicar nas 1 notas',exact=True).click()
            page.get_by_text('1 notas atualizadas. Estoque e financeiro não foram movimentados.',exact=True).wait_for()
            self.assertEqual(page.get_by_role('link',name='123 / 1',exact=True).count(),0)
            page.locator('#status').select_option('IGNORED');page.get_by_role('button',name='Filtrar',exact=True).click()
            page.locator('input[name="selected"]').check()
            page.get_by_role('button',name='Ignorar / modificar em massa',exact=True).click()
            page.locator('#id_action').select_option('reopen')
            page.get_by_role('button',name='Revisar alterações',exact=True).click()
            page.get_by_role('button',name='Aplicar nas 1 notas',exact=True).click()
            page.get_by_text('1 notas atualizadas. Estoque e financeiro não foram movimentados.',exact=True).wait_for()
            page.get_by_role('link',name='123 / 1',exact=True).wait_for()
            browser.close()
        invoice.refresh_from_db();self.assertEqual(invoice.status,'PENDING')

    def test_purchase_new_product_and_financial_only_item(self):
        from playwright.sync_api import sync_playwright
        from django.urls import reverse
        from apps.purchases.models import Supplier, Purchase
        from apps.products.models import Product
        from apps.expenses.models import ChartOfAccount
        from .test_purchase_import import incoming, SUPPLIER
        from .purchase_services import stage as stage_purchase
        from pathlib import Path
        connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        Supplier.objects.create(legal_name='Fornecedor sintético',document=SUPPLIER)
        category=ChartOfAccount.objects.create(code='04',name='Embalagens sintéticas',nature='OPERATING')
        data=incoming(valorNota='110',parcelas=[]);data['itens'][0]['codigo']=''
        data['itens'].append(dict(data['itens'][0],descricao='Caixas sintéticas',quantidade=1,valor=10))
        invoice=stage_purchase(actor=self.actor,connection=connection,payload=data)
        client=Client();client.force_login(self.actor)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(self.live_server_url+reverse('bling_purchase_detail',args=[invoice.pk]))
            page.locator('#id_location').select_option(str(self.location.pk))
            page.locator('#id_products-0-mode').select_option('NEW')
            page.locator('#id_products-0-new_sku').fill('NEW-BROWSER')
            page.locator('#id_products-0-new_name').fill('Produto com nome local')
            page.locator('#id_products-1-mode').select_option('NONSTOCK')
            page.locator('#id_products-1-category').select_option(str(category.pk))
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/bling-purchase-mixed-desktop.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            control=page.locator('#id_products-0-new_name').bounding_box()
            self.assertGreaterEqual(control['x'],0)
            self.assertLessEqual(control['x']+control['width'],390)
            page.screenshot(path='artifacts/bling-purchase-mixed-mobile.png',full_page=True)
            page.locator('#id_reviewed').check()
            page.get_by_role('button',name='Importar rascunho de compra',exact=True).click()
            page.get_by_text('Rascunho importado.',exact=False).wait_for()
            self.assertEqual(errors,[]);browser.close()
        p=Purchase.objects.get();self.assertEqual(p.total,110)
        self.assertEqual(p.items.get(moves_stock=False).nonstock_total,10)
        self.assertTrue(Product.objects.filter(sku='NEW-BROWSER',name='Produto com nome local').exists())
