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
