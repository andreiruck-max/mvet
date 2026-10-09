from types import SimpleNamespace
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.sales.models import Sale
from apps.inventory.models import StockMovement
from . import bling


class PeriodQueryTests(Fixture, TestCase):
    def test_manual_invoice_without_store_found_by_number(self):
        from urllib.parse import urlparse,parse_qs
        from .tests import payload,ISSUER
        from .models import BlingConnection,InvoiceImport
        BlingConnection.objects.create(pk=1,issuer=ISSUER,tokens='synthetic')
        doc=payload(loja=None,numeroPedidoLoja=None)
        with patch.object(bling,'read',side_effect=[{'data':[{'id':1000}]},{'data':doc}]) as read:
            run=bling.sync_page(actor=self.actor,start=timezone.localdate(),end=timezone.localdate(),number=123,series=1)
        params=parse_qs(urlparse(read.call_args_list[0].args[0]).query)
        self.assertEqual(params['numero'],['123']);self.assertEqual(params['serie'],['1'])
        self.assertNotIn('situacao',params);self.assertNotIn('dataEmissaoInicial',params);self.assertNotIn('idLoja',params)
        self.assertEqual(run.processed,1);self.assertEqual(run.errors,0)
        invoice=InvoiceImport.objects.get();self.assertEqual(invoice.status,'PENDING');self.assertEqual(invoice.source['store'],'')

    def test_combined_query_keeps_paging_until_both_statuses_end(self):
        from urllib.parse import urlparse, parse_qs
        from .tests import payload, ISSUER
        from .models import BlingConnection, InvoiceImport
        from .forms import QueryForm
        BlingConnection.objects.create(pk=1, issuer=ISSUER, tokens='synthetic')
        self.assertEqual(QueryForm()['source_status'].value(), 56)
        doc = payload(situacao=6, loja=None)
        # Empty authorized page must not hide a full printed page.
        with patch.object(bling, 'read', side_effect=[{'data': []},
                {'data': [{'id': 1000}] * bling.PAGE_SIZE}, {'data': doc}]) as read:
            run = bling.sync_page(actor=self.actor, start=timezone.localdate(), end=timezone.localdate(), source_status=56)
        self.assertEqual([parse_qs(urlparse(c.args[0]).query)['situacao'] for c in read.call_args_list[:2]], [['5'], ['6']])
        self.assertTrue(run.has_more)
        self.assertEqual(run.processed, 1)
        self.assertEqual(run.errors, 0)
        self.assertEqual(InvoiceImport.objects.get().status, 'PENDING')
        with patch.object(bling, 'read', side_effect=[{'data': []}, {'data': []}]):
            run = bling.sync_page(actor=self.actor, start=timezone.localdate(), end=timezone.localdate(), page=2, source_status=56)
        self.assertFalse(run.has_more)

    def test_explicit_danfe_filter_is_accepted(self):
        self.values['source_status'] = 6
        with patch('apps.integrations.views.bling.sync_page', return_value=SimpleNamespace(page=1, processed=0, errors=0, has_more=False, message='')) as sync:
            self.assertEqual(self.post().status_code, 200)
        self.assertEqual(sync.call_args.kwargs['source_status'], 6)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.actor)
        self.values = {'start': str(timezone.localdate()), 'end': str(timezone.localdate()), 'source_status': 5, 'page': 1}

    def post(self):
        return self.client.post(reverse('bling_query'), self.values, HTTP_ACCEPT='application/json')

    def test_full_page_advances_even_with_document_errors_without_sale(self):
        before = StockMovement.objects.count()
        with patch('apps.integrations.views.bling.sync_page', return_value=SimpleNamespace(page=1, processed=5, errors=2, has_more=True, message='')) as sync:
            result = self.post()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['next_page'], 2)
        self.assertFalse(result.json()['blocked'])
        self.assertEqual(result.json()['errors'], 2)
        self.assertEqual(sync.call_args.kwargs['actor'], self.actor)
        self.assertFalse(Sale.objects.exists())
        self.assertEqual(before, StockMovement.objects.count())

    def test_partial_failure_does_not_skip_page(self):
        with patch('apps.integrations.views.bling.sync_page', return_value=SimpleNamespace(page=1, processed=2, errors=1, has_more=True, message='Limite atingido')):
            result = self.post().json()
        self.assertTrue(result['blocked'])
        self.assertEqual(result['next_page'], 1)

    def test_last_page_finishes_and_page_limit_stops(self):
        with patch('apps.integrations.views.bling.sync_page', return_value=SimpleNamespace(page=1, processed=0, errors=0, has_more=False, message='')):
            self.assertIsNone(self.post().json()['next_page'])
        self.values['page'] = 10000
        with patch('apps.integrations.views.bling.sync_page', return_value=SimpleNamespace(page=10000, processed=5, errors=0, has_more=True, message='')):
            self.assertTrue(self.post().json()['blocked'])

    def test_invalid_and_disconnected_requests_are_json_errors(self):
        self.values['page'] = 0
        with patch('apps.integrations.views.bling.sync_page') as sync:
            self.assertEqual(self.post().status_code, 400)
            sync.assert_not_called()
        self.values['page'] = 1
        with patch('apps.integrations.views.bling.sync_page', side_effect=bling.BlingError('Conecte o Bling')):
            self.assertEqual(self.post().json()['message'], 'Conecte o Bling')

    def test_permissions_and_csrf_still_required(self):
        with patch('apps.integrations.views.bling.sync_page') as sync:
            self.client.force_login(self.operator)
            self.assertEqual(self.post().status_code, 403)
            secured = Client(enforce_csrf_checks=True); secured.force_login(self.actor)
            self.assertEqual(secured.post(reverse('bling_query'), self.values, HTTP_ACCEPT='application/json').status_code, 403)
            sync.assert_not_called()
