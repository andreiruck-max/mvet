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
            page.get_by_role('link', name='123 / 1', exact=True).click()
            page.get_by_text('Vínculo pendente', exact=True).wait_for()
            page.locator('summary').click()
            page.get_by_label('Código externo:', exact=True).fill('EXT-DEMO')
            page.get_by_label('Unidade externa:', exact=True).fill('UN')
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
            page.get_by_label('Valor (R$):', exact=True).fill('2')
            page.locator('#id_reviewed').check()
            self.assertIsNotNone(page.locator('#id_purpose_reviewed').get_attribute('required'))
            page.locator('#id_purpose_reviewed').check()
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
