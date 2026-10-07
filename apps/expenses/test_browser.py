import os
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from apps.core.models import Company
from apps.finance.models import FinancialEntry, FinancialTitle
from apps.finance.services import save_account
from .models import Expense
from .services import save_category, save_rule


@skipUnless(os.environ.get('MVET_BROWSER_TESTS')=='1','Browser acceptance is enabled in CI')
@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ExpenseBrowser(StaticLiveServerTestCase):
    def test_suggested_code_and_optional_counterparty_with_category_search(self):
        from playwright.sync_api import sync_playwright, expect
        Company.objects.create(pk=1);actor=User.objects.create_superuser('expense-form-browser')
        root=save_category(actor=actor,data=dict(code='04',name='Despesas operacionais',nature='OPERATING',postable=False))
        root_id=str(root.pk)
        client=Client();client.force_login(actor);output=Path('artifacts');output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1000},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
            page.goto(self.live_server_url+'/despesas/categorias/nova/')
            expect(page.locator('#id_code')).to_have_value('05')
            page.locator('#id_parent').select_option(root_id)
            expect(page.locator('#id_code')).to_have_value('04.01')
            page.locator('#id_code').fill('04.15')
            page.locator('#id_parent').select_option('')
            expect(page.locator('#id_code')).to_have_value('04.15')
            page.locator('#id_parent').select_option(root_id)
            page.get_by_role('button',name='Usar código sugerido').click()
            expect(page.locator('#id_code')).to_have_value('04.01')
            page.locator('#id_name').fill('Contabilidade')
            page.screenshot(path=str(output/'expense-category-desktop.png'),full_page=True)
            page.get_by_role('button',name='Salvar configuração').click()
            page.get_by_text('Configuração salva. Despesas anteriores foram preservadas.',exact=True).wait_for()
            page.goto(self.live_server_url+'/despesas/nova/')
            page.locator('#id_description').fill('Serviço sem cadastro')
            page.locator('#id_amount').fill('150')
            page.locator('#id_counterparty').fill('Prestador avulso')
            page.locator('#category-search').fill('contabilidade')
            page.locator('#id_category').select_option(label='04.01 · Despesas operacionais / Contabilidade')
            selected=page.locator('#id_category').input_value()
            page.locator('#category-search').fill('sem resultado')
            expect(page.locator('#id_category')).to_have_value(selected)
            page.locator('#category-search').fill('')
            page.screenshot(path=str(output/'expense-new-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output/'expense-new-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            page.get_by_role('button',name='Registrar despesa',exact=True).click()
            page.get_by_role('heading',name='Serviço sem cadastro',exact=True).wait_for()
            self.assertEqual(errors,[]);browser.close()
        obj=Expense.objects.get();self.assertIsNone(obj.supplier_id)
        self.assertEqual(obj.counterparty,'Prestador avulso');self.assertEqual(obj.category.code,'04.01')
        self.assertEqual(obj.title.amount,150);self.assertFalse(FinancialEntry.objects.exists())

    def test_classification_payment_and_monthly_recurrence(self):
        from playwright.sync_api import sync_playwright
        today=timezone.localdate();Company.objects.create(pk=1)
        actor=User.objects.create_superuser('expense-browser')
        category=save_category(actor=actor,data=dict(code='04',name='Contabilidade',nature='OPERATING'))
        save_rule(actor=actor,data=dict(name='Honorários',field='description',operator='CONTAINS',value='contabilidade',category=category))
        save_account(actor=actor,data=dict(name='Conta de teste',kind='BANK',opening_date=today,opening_balance=Decimal('1000')))
        client=Client();client.force_login(actor);output=Path('artifacts');output.mkdir(exist_ok=True)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1050},locale='pt-BR')
            context.add_cookies([{'name':'sessionid','value':client.cookies['sessionid'].value,'url':self.live_server_url}])
            page=context.new_page();errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
            page.goto(self.live_server_url+'/despesas/nova/')
            page.get_by_label('Descrição:',exact=True).fill('Contabilidade mensal')
            page.get_by_label('Valor (R$):',exact=True).fill('100')
            page.get_by_label('Conta prevista:',exact=True).select_option(label='Conta de teste')
            page.get_by_label('Despesa recorrente mensal:',exact=True).check()
            page.get_by_role('button',name='Registrar despesa',exact=True).click()
            page.get_by_role('heading',name='Contabilidade mensal',exact=True).wait_for()
            detail_url=page.url
            page.get_by_role('link',name='Abrir pagamento no financeiro',exact=True).click()
            page.get_by_role('button',name='Confirmar liquidação',exact=True).click()
            page.get_by_text('Operação financeira confirmada.',exact=True).wait_for()
            page.goto(detail_url)
            page.screenshot(path=str(output/'expense-detail-desktop.png'),full_page=True)
            page.get_by_role('link',name='Preparar próximos meses',exact=True).click()
            page.get_by_label('Próximos meses (1 a 24):',exact=True).fill('2')
            page.get_by_role('button',name='Revisar prévia',exact=True).click()
            page.get_by_role('button',name='Confirmar geração',exact=True).click()
            page.get_by_text('2 despesas geradas. Ocorrências existentes não foram duplicadas.',exact=True).wait_for()
            page.get_by_role('link',name='Relatório por competência',exact=True).click()
            page.get_by_role('heading',name='Despesas por competência',exact=True).wait_for()
            page.screenshot(path=str(output/'expense-report-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'expense-report-mobile.png'),full_page=True)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),390)
            self.assertEqual(errors,[]);browser.close()
        self.assertEqual(Expense.objects.count(),3);self.assertEqual(FinancialTitle.objects.count(),3)
        self.assertEqual(FinancialEntry.objects.count(),1)
        obj=Expense.objects.get(recurrence_of__isnull=True)
        self.assertEqual(obj.classification,'RULE')
        obj.title.refresh_from_db();self.assertEqual(obj.title.remaining,0)
        self.assertEqual(sum(x.title.remaining for x in obj.occurrences.select_related('title')),200)
