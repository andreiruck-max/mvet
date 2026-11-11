from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch
from django.contrib.auth.models import User, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.finance.models import FinancialAccount, FinancialEntry, FinancialOperation, FinancialTitle
from apps.inventory.models import StockMovement
from .models import BlingConnection, BlingBankAccount, BlingBankLink, BlingBankRun, BlingBankEntry, BlingBankDay
from . import bank_services as svc


@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BankTests(TestCase):
    def setUp(self):
        self.actor=User.objects.create_superuser('bank-owner')
        self.today=timezone.localdate(); self.start=self.today-timedelta(days=2)
        self.conn=BlingConnection.objects.create(pk=1,issuer='12345678000195',tokens='synthetic')
        self.account=FinancialAccount.objects.create(name='Carteira teste',kind='WALLET',opening_date=self.start,opening_balance=D('100'))
        self.external=BlingBankAccount.objects.create(connection=self.conn,external_id='12',description='Carteira externa')
        self.link=svc.configure(actor=self.actor,account_id=self.account.pk,external=self.external,start_date=self.start,opening_balance=D('100'),automatic=True)

    def row(self, id='1', **changes):
        return dict(dict(id=id,contaFinanceira={'id':12},data=str(self.today),debCred='C',situacao='R',valor='1200.00',descricao='Liberações'),**changes)

    def queue(self,start=None,end=None):
        return svc.enqueue(actor=self.actor,link_id=self.link.pk,start=start or self.start,end=end or self.today)

    def page(self,run,data):
        run.refresh_from_db()
        with patch('apps.integrations.bling.read', return_value={'data':data}) as read:
            svc.process_page(run)
        run.refresh_from_db()
        return read

    def complete(self,run,data):
        self.page(run,data); self.page(run,[]); self.page(run,[])
        self.assertEqual(run.status,'DONE')

    def test_atomic_pagination_idempotence_and_net_many_to_one(self):
        other=FinancialAccount.objects.create(name='Origem sintética',kind='BANK',opening_date=self.start)
        operation=FinancialOperation.objects.create(actor=self.actor,date=self.today,kind='TRANSFER',status='POSTED',fingerprint='synthetic',description='Liberação consolidada',actual=1000)
        FinancialEntry.objects.create(operation=operation,account=other,amount=-1000)
        FinancialEntry.objects.create(operation=operation,account=self.account,amount=1000)
        run=self.queue()
        self.page(run,[self.row()])
        self.assertFalse(self.link.entries.exists())
        self.page(run,[self.row('2',debCred='D',valor='200')])
        self.page(run,[]); self.page(run,[])
        self.assertEqual(run.status,'DONE')
        c=svc.comparison(self.link,self.start,self.today)
        self.assertEqual(c['net_difference'],0);self.assertEqual(c['balance_difference'],0)
        self.assertEqual(c['remote_balance'],1100)
        self.assertEqual(self.link.entries.count(),2)
        self.assertEqual(FinancialEntry.objects.count(),2)
        self.assertEqual(FinancialTitle.objects.count(),0);self.assertEqual(StockMovement.objects.count(),0)
        second=self.queue();self.complete(second,[self.row(),self.row('2',debCred='D',valor='200')])
        self.assertEqual(self.link.entries.count(),2)

    def test_failure_preserves_previous_statement_and_retries(self):
        self.complete(self.queue(),[self.row()])
        run=self.queue();self.page(run,[self.row(valor='999')])
        with patch('apps.integrations.bling.read',side_effect=ValidationError('Falha temporária')):
            svc.process_page(run)
        run.refresh_from_db();self.assertEqual(run.page,2);self.assertEqual(run.status,'QUEUED')
        self.assertEqual(self.link.entries.get().amount,1200)
        self.assertGreater(run.next_attempt,timezone.now())
        self.page(run,[]);self.page(run,[])
        self.assertEqual(self.link.entries.get().amount,999)

    def test_excluded_missing_and_changed_rows_retained(self):
        self.complete(self.queue(),[self.row(),self.row('2')])
        run=self.queue();self.page(run,[])
        self.page(run,[self.row(situacao='E')]);self.page(run,[])
        self.assertTrue(self.link.entries.get(external_id='1').deleted)
        self.assertFalse(self.link.entries.get(external_id='2').present)
        self.assertEqual(self.link.entries.count(),2)
        self.assertEqual(svc.comparison(self.link,self.start,self.today)['remote_net'],0)

    def test_no_false_zero_for_unknown_days_or_missing_opening(self):
        self.complete(self.queue(start=self.today),[self.row()])
        c=svc.comparison(self.link,self.start,self.today)
        self.assertIsNone(c['remote_net']);self.assertIsNone(c['remote_balance'])
        self.assertEqual(svc.comparison(self.link,self.today,self.today)['remote_net'],1200)
        self.link.opening_balance=None; self.link.save()
        self.assertIsNone(svc.comparison(self.link,self.today,self.today)['remote_balance'])

    def test_automatic_coalesces_requests_fills_gap_and_runs_on_each_visit(self):
        self.complete(self.queue(end=self.today-timedelta(days=1)),[])
        run=svc.enqueue(actor=self.actor,link_id=self.link.pk,automatic=True)
        self.assertEqual(run.start,self.today-timedelta(days=1));self.assertEqual(run.end,self.today)
        self.assertEqual(svc.enqueue(actor=self.actor,link_id=self.link.pk,automatic=True).pk,run.pk)
        self.complete(run,[])
        next_run=svc.enqueue(actor=self.actor,link_id=self.link.pk,automatic=True)
        self.assertEqual(next_run.start,self.today);self.assertNotEqual(next_run.pk,run.pk)
        self.link.automatic=False;self.link.save()
        self.assertIsNone(svc.enqueue(actor=self.actor,link_id=self.link.pk,automatic=True))

    def test_opening_during_historical_import_still_schedules_today(self):
        old=self.queue(end=self.start)
        self.assertEqual(svc.enqueue(actor=self.actor,link_id=self.link.pk,automatic=True).pk,old.pk)
        self.complete(old,[])
        follow=self.link.runs.get(status='QUEUED')
        self.assertEqual(follow.end,self.today)

    def test_invalid_wrong_account_precision_and_repeated_pages_never_publish(self):
        for changes in ({'contaFinanceira':{'id':99}},{'valor':'NaN'},{'valor':'1.001'},{'debCred':'?'},{'data':str(self.today+timedelta(days=1))}):
            run=self.queue();self.page(run,[self.row(**changes)])
            self.assertEqual(run.status,'QUEUED');self.assertFalse(self.link.entries.exists())
            run.status='FAILED';run.save()
        run=self.queue();self.page(run,[self.row()]);self.page(run,[self.row()])
        self.assertEqual(run.page,2);self.assertEqual(run.status,'QUEUED');self.assertFalse(self.link.entries.exists())

    def test_permissions_csrf_read_only_gets_and_revocation(self):
        user=User.objects.create_user('bank-no-access')
        self.client.force_login(user)
        for name in ['financial_account','bling_bank_statement','bling_bank_status','bling_bank_settings']:
            self.assertEqual(self.client.get(reverse(name,args=[self.account.pk])).status_code,403)
        with self.assertRaises(PermissionDenied):svc.enqueue(actor=user,link_id=self.link.pk,automatic=True)
        self.client.force_login(self.actor)
        with patch('apps.integrations.bling.read') as read:
            for name in ['financial_account','bling_bank_statement','bling_bank_status']:
                self.assertEqual(self.client.get(reverse(name,args=[self.account.pk])).status_code,200)
            read.assert_not_called()
        self.assertEqual(BlingBankRun.objects.count(),0)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.actor)
        self.assertEqual(csrf.post(reverse('bling_bank_refresh',args=[self.account.pk]),{'mode':'automatic'}).status_code,403)
        self.assertEqual(self.client.post(reverse('bling_bank_refresh',args=[self.account.pk]),{'mode':'automatic'}).status_code,200)
        run=self.link.runs.get();self.actor.is_active=False;self.actor.save()
        with patch('apps.integrations.bling.read') as read:svc.tick();read.assert_not_called()
        run.refresh_from_db();self.assertEqual(run.status,'FAILED')

    def test_mapping_unique_and_catalog_paging(self):
        with patch('apps.integrations.bling.read',return_value={'data':[{'id':12,'descricao':'Nome atualizado'}]}) as read:
            self.assertTrue(svc.fetch_accounts(actor=self.actor,page=1))
        self.external.refresh_from_db();self.assertEqual(self.external.description,'Nome atualizado')
        self.assertIn('ocultarTipoContaBancaria=false',read.call_args.args[0])
        other=FinancialAccount.objects.create(name='Outra',kind='BANK',opening_date=self.start)
        with self.assertRaises(ValidationError):
            svc.configure(actor=self.actor,account_id=other.pk,external=self.external,start_date=self.start,opening_balance=0,automatic=True)

    def test_future_and_planned_local_movements_do_not_enter_comparison(self):
        other=FinancialAccount.objects.create(name='Outra origem',kind='BANK',opening_date=self.start)
        for status,day in [('PLANNED',self.today),('POSTED',self.today+timedelta(days=1))]:
            op=FinancialOperation.objects.create(actor=self.actor,date=day,kind='TRANSFER',status=status,fingerprint=status,description='Sintético',actual=50)
            FinancialEntry.objects.create(operation=op,account=self.account,amount=50)
            FinancialEntry.objects.create(operation=op,account=other,amount=-50)
        self.complete(self.queue(),[])
        self.assertEqual(svc.comparison(self.link,self.start,self.today)['local_balance'],100)
