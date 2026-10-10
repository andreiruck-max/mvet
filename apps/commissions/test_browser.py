import os
from pathlib import Path
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client,override_settings
from django.urls import reverse
from .tests import Fixture
from .models import CommissionPlan,Payment

@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CommissionBrowser(Fixture,StaticLiveServerTestCase):
    def test_create_receive_partial_pay_monthly_and_employee_mobile(self):
        from playwright.sync_api import sync_playwright,expect
        client=Client();client.force_login(self.actor)
        employee=Client();employee.force_login(self.employee)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.live_server_url+reverse('commission_sale',args=[self.sale.pk]))
            page.get_by_label('Comissionado:',exact=True).select_option(str(self.payee.pk))
            page.get_by_label('Cliente (somente identificação):',exact=True).fill('Cliente de demonstração')
            page.get_by_label('Quantidade de parcelas iguais:',exact=True).fill('2')
            page.get_by_role('button',name='Salvar',exact=True).click()
            expect(page.get_by_role('heading',name='Parcelas',exact=True)).to_be_visible()
            page.get_by_role('link',name='Registrar recebimento',exact=True).first.click()
            page.get_by_label('Valor recebido (R$):',exact=True).fill('475.00')
            page.get_by_label('Motivo / observação:',exact=True).fill('Recebimento de teste confirmado')
            page.get_by_role('button',name='Salvar',exact=True).click()
            expect(page.get_by_text('Operação registrada com histórico.',exact=True)).to_be_visible()
            page.get_by_role('link',name='Revisar parcelas',exact=True).click()
            page.get_by_label('Motivo / observação:',exact=True).fill('Conferência do cronograma')
            page.get_by_role('button',name='Salvar cronograma',exact=True).click()
            expect(page.get_by_text('Cronograma revisado, com histórico e ajuste da liberação.',exact=True)).to_be_visible()
            Path('artifacts').mkdir(exist_ok=True)
            page.screenshot(path='artifacts/commissions-detail-desktop.png',full_page=True)
            page.goto(self.live_server_url+reverse('commission_payment_new'))
            page.get_by_label('Comissionado:',exact=True).select_option(str(self.payee.pk))
            page.get_by_label('Valor pago (R$):',exact=True).click()
            page.get_by_label('Valor pago (R$):',exact=True).press_sequentially('1000')
            page.get_by_label('Motivo / observação:',exact=True).fill('Pagamento parcial de teste')
            page.get_by_role('button',name='Salvar',exact=True).click()
            expect(page.get_by_text('Pagamento registrado e alocado',exact=False)).to_be_visible()
            page.goto(self.live_server_url+reverse('commission_monthly'))
            expect(page.locator('main')).to_contain_text('12,50')
            page.screenshot(path='artifacts/commissions-monthly-desktop.png',full_page=True)
            page.goto(self.live_server_url+reverse('commissions'))
            page.screenshot(path='artifacts/commissions-index-desktop.png',full_page=True)
            mobile=browser.new_context(viewport={'width':390,'height':844})
            mobile.add_cookies([{'name':'sessionid','value':employee.cookies['sessionid'].value,'url':self.live_server_url}])
            p=mobile.new_page();p.goto(self.live_server_url+reverse('commissions'))
            expect(p.get_by_role('link',name='Definir comissão de venda',exact=True)).to_have_count(0)
            self.assertLessEqual(p.evaluate('document.documentElement.scrollWidth'),390)
            p.screenshot(path='artifacts/commissions-employee-mobile.png',full_page=True)
            self.assertEqual(errors,[]);browser.close()
        self.assertEqual(CommissionPlan.objects.get().total,45)
        self.assertEqual(Payment.objects.get().amount,10)
