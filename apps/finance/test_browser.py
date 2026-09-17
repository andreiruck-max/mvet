import os
from pathlib import Path
from decimal import Decimal
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from apps.core.models import Company
from .models import FinancialAccount as Account, FinancialTitle as Title, FinancialEntry as Entry
from .services import save_account


@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class FinanceBrowser(StaticLiveServerTestCase):
    def test_title_partial_payment_transfer_and_daily_cash(self):
        from playwright.sync_api import sync_playwright
        today=timezone.localdate();Company.objects.create(pk=1)
        actor=User.objects.create_superuser('finance-browser')
        save_account(actor=actor,data=dict(name='Conta A',kind='BANK',opening_date=today,opening_balance=Decimal('1000')))
        save_account(actor=actor,data=dict(name='Conta B',kind='BANK',opening_date=today,opening_balance=Decimal('0')))
        client=Client();client.force_login(actor);output=Path('artifacts');output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
            page.goto(self.live_server_url+'/financeiro/titulos/novo/')
            page.get_by_label('Tipo:',exact=True).select_option('PAY')
            page.get_by_label('Descrição:',exact=True).fill('Pagamento de demonstração')
            page.get_by_label('Valor principal (R$):',exact=True).fill('100')
            page.get_by_label('Conta prevista:',exact=True).select_option(label='Conta A')
            page.get_by_role('button',name='Registrar título',exact=True).click()
            page.get_by_role('heading',name='Marcar como pago',exact=True).wait_for()
            page.get_by_label('Principal a baixar (R$):',exact=True).fill('40')
            page.get_by_label('Valor efetivamente pago / recebido (R$):',exact=True).fill('40')
            page.get_by_role('button',name='Confirmar liquidação',exact=True).click()
            page.get_by_text('Operação financeira confirmada.',exact=True).wait_for()
            page.screenshot(path=str(output/'finance-partial-desktop.png'),full_page=True)
            page.get_by_role('link',name='Transferir entre contas',exact=True).click()
            page.get_by_label('Conta de origem:',exact=True).select_option(label='Conta A')
            page.get_by_label('Conta de destino:',exact=True).select_option(label='Conta B')
            page.get_by_label('Valor (R$):',exact=True).fill('200')
            page.get_by_role('button',name='Confirmar transferência',exact=True).click()
            page.get_by_role('heading',name='Transferência #',exact=False).wait_for()
            page.get_by_role('link',name='Fluxo diário',exact=True).click()
            page.get_by_label('Até:',exact=True).fill(today.isoformat())
            page.get_by_role('button',name='Consultar',exact=True).click()
            page.screenshot(path=str(output/'finance-cash-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'finance-cash-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            self.assertEqual(errors,[]);browser.close()
        title=Title.objects.get();self.assertEqual(title.settled,40);self.assertEqual(title.remaining,60)
        self.assertEqual(Entry.objects.count(),3)
