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
