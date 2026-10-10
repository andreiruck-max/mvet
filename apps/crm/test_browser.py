import os
from pathlib import Path
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.urls import reverse
from .tests import Fixture
from .models import Contact, Interaction

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CRMBrowser(Fixture,StaticLiveServerTestCase):
    def test_employee_create_contact_context_recurrence_mobile_and_master_approval(self):
        from playwright.sync_api import sync_playwright, expect
        client=Client();client.force_login(self.worker)
        master_client=Client();master_client.force_login(self.master)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.live_server_url+reverse('crm_new'))
            page.get_by_label('Nome:',exact=True).fill('João de demonstração')
            page.get_by_label('Telefone / WhatsApp:',exact=True).fill('(45) 99999-0234')
            page.get_by_label('Cidade (recomendada):',exact=True).fill('Cidade de teste')
            page.get_by_label('Informações comerciais importantes:',exact=True).fill('Prefere contato por WhatsApp; compra mensalmente.')
            page.get_by_role('button',name='Salvar',exact=True).click()
            expect(page.locator('h1')).to_have_text('João de demonstração')
            self.assertTrue(page.get_by_role('link',name='Abrir WhatsApp',exact=True).get_attribute('href').endswith('5545999990234'))
            page.get_by_role('link',name='Registrar contato',exact=True).click()
            page.get_by_label('Mensagem enviada:',exact=True).fill('Bom dia João!\nComo está seu estoque?')
            page.get_by_label('Mensagem recebida:',exact=True).fill('Me chame daqui a três semanas.')
            page.get_by_label('Resultado:',exact=True).select_option('CALLBACK')
            page.get_by_role('button',name='+30 dias',exact=True).click()
            expect(page.locator('#crm-suggestion')).to_contain_text('escolhido')
            page.get_by_role('button',name='Concluir contato',exact=True).click()
            expect(page.locator('h1')).to_have_text('João de demonstração')
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/crm-contact-desktop.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.screenshot(path='artifacts/crm-contact-mobile.png',full_page=True)
            page.get_by_role('link',name='Solicitar inativação',exact=True).click()
            page.get_by_label('Motivo:',exact=True).select_option('OUTSIDE')
            page.get_by_label('Justificativa / contexto:',exact=True).fill('Não atua mais no segmento.')
            page.get_by_role('button',name='Salvar',exact=True).click()
            expect(page.locator('main .badge')).to_have_text('Solicitação de inativação')
            context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':master_client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page()
            response=page.goto(self.live_server_url+reverse('crm_approvals'))
            self.assertEqual(response.status,200,page.locator('body').inner_text())
            page.screenshot(path='artifacts/crm-approvals-desktop.png',full_page=True)
            page.get_by_role('link',name='Analisar solicitação',exact=True).click()
            page.get_by_role('button',name='Registrar decisão',exact=True).click()
            expect(page.get_by_text('Nenhuma solicitação pendente.',exact=True)).to_be_visible()
            self.assertEqual(errors,[]);browser.close()
        self.assertEqual(Contact.objects.get().owner,self.worker)
        self.assertEqual(Interaction.objects.get().read_state,'UNKNOWN')
        self.assertEqual(Contact.objects.get().state,'INACTIVE')

    def test_master_import_preview_and_rules(self):
        from playwright.sync_api import sync_playwright, expect
        client=Client();client.force_login(self.master)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();page.goto(self.live_server_url+reverse('crm_import'))
            page.get_by_label('Lista CSV ou XLSX:',exact=True).set_input_files({'name':'test.csv','mimeType':'text/csv','buffer':b'nome,email\nCRM Importado,import@example.com'})
            page.get_by_label('Responsável padrão:',exact=True).select_option(str(self.worker.pk))
            page.get_by_role('button',name='Validar e visualizar prévia',exact=True).click()
            expect(page.get_by_text('Pronto para importar',exact=True)).to_be_visible()
            page.get_by_role('checkbox').check();page.get_by_role('button',name='Confirmar importação',exact=True).click()
            expect(page.get_by_role('heading',name='Resultado da importação')).to_be_visible()
            page.goto(self.live_server_url+reverse('crm_rules'))
            page.get_by_role('button',name='Salvar regras',exact=True).click()
            expect(page.get_by_text('Regras salvas.',exact=False)).to_be_visible()
            page.goto(self.live_server_url+reverse('crm_queue'))
            Path('artifacts').mkdir(exist_ok=True);page.screenshot(path='artifacts/crm-queue-desktop.png',full_page=True)
            browser.close()
        self.assertEqual(Contact.objects.count(),1)
