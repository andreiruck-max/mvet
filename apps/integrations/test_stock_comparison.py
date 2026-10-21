from decimal import Decimal as D
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.products.pricing import sale_price, configure_fixed_price
from apps.inventory.models import StockMovement, StockBalance
from . import bling, stock_comparison as service
from .models import BlingStockCorrection


class StockComparisonTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.company.default_stock_location = self.location
        self.company.save()
        self.remote_price = D('9.10')
        self.remote_quantity = D('7')
        self.remote_calls = []
        self.mock = patch('apps.integrations.bling.read', side_effect=self.remote)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def remote(self, path, *, method='GET', payload=None):
        if method != 'GET':
            self.remote_calls.append((path, method, payload))
            if method == 'PATCH': self.remote_price = payload['preco']
            else: self.remote_quantity = payload['quantidade']
            return {'data': {'id': 900}}
        if path.startswith('/depositos'):
            return {'data': [{'id': 42, 'descricao': 'Loja externa', 'situacao': 1}]}
        product = {'nome': 'Produto externo', 'id': 99, 'codigo': self.product.sku, 'preco': self.remote_price,
                   'tipo': 'P', 'formato': 'S', 'situacao': 'A'}
        if path.startswith('/produtos?'):
            return {'data': [product]}  # Real list schema does not include unidade.
        if path == '/produtos/99': return {'data': dict(product, unidade='UN')}
        if path.startswith('/estoques/saldos/42?'):
            self.assertEqual(parse_qs(urlsplit(path).query)['idsProdutos[]'], ['99'])
            return {'data': [{'produto': {'id': 99}, 'saldoFisicoTotal': self.remote_quantity}]}
        raise AssertionError(path)

    def row(self):
        return service.comparison(actor=self.actor, products=[self.product], location=self.location, deposit='42')[0]

    def apply(self, row, field='price', direction='mvet'):
        return service.apply(actor=self.actor, token=row['token'], field=field, direction=direction, reason='Conferência sintética')

    def test_prices_both_directions_and_fixed_zero(self):
        result = self.apply(self.row())
        self.assertEqual(result.status, 'DONE')
        self.product.refresh_from_db()
        self.assertEqual(sale_price(self.product, D(50), D(35)), D('9.10'))
        configure_fixed_price(actor=self.actor, product_id=self.product.pk, price=D('0'))
        result = self.apply(self.row(), direction='bling')
        self.assertEqual(result.status, 'DONE')
        self.assertEqual(self.remote_price, 0)
        self.assertEqual(self.remote_calls[0], ('/produtos/99', 'PATCH', {'preco': D(0)}))
        configure_fixed_price(actor=self.actor, product_id=self.product.pk, price=None)
        self.product.refresh_from_db()
        self.assertEqual(sale_price(self.product, D(5), D(35)), D('6.75'))

    def test_stock_both_directions_no_historic_cmv_change_and_replay(self):
        sale = self.confirmed()
        cmv = sale.cmv
        row = self.row()
        result = self.apply(row, field='quantity')
        self.assertEqual(result.status, 'DONE')
        count = StockMovement.objects.count()
        self.assertEqual(self.apply(row, field='quantity').pk, result.pk)
        self.assertEqual(StockMovement.objects.count(), count)
        self.assertEqual(StockBalance.objects.get(product=self.product, location=self.location).quantity, 7)
        sale.refresh_from_db()
        self.assertEqual(sale.cmv, cmv)
        self.remote_quantity = D(2)
        result = self.apply(self.row(), field='quantity', direction='bling')
        self.assertEqual(result.status, 'DONE')
        self.assertEqual(self.remote_quantity, 7)
        self.assertEqual(self.remote_calls[0][2]['deposito'], {'id': 42})
        self.assertEqual(self.remote_calls[0][2]['operacao'], 'B')
        self.assertNotIn('custo', self.remote_calls[0][2])

    def test_stale_local_and_remote_refused(self):
        row = self.row()
        self.receive(self.product, D(1), D(5))
        with self.assertRaises(ValidationError): self.apply(row)
        row = self.row()
        self.remote_price = D(10)
        result = self.apply(row)
        self.assertEqual(result.status, 'FAILED')
        self.product.refresh_from_db()
        self.assertIsNone(self.product.fixed_sale_price)
        self.assertFalse(self.remote_calls)

    def test_ambiguous_remote_failure_never_automatically_retried(self):
        row = self.row()
        original = self.remote
        def failed(path, **kwargs):
            if kwargs.get('method') == 'PATCH':
                original(path, **kwargs)
                raise bling.BlingError('Resposta perdida')
            return original(path, **kwargs)
        with patch('apps.integrations.bling.read', side_effect=failed):
            result = self.apply(row, direction='bling')
            self.assertEqual(result.status, 'UNKNOWN')
            self.assertEqual(self.apply(row, direction='bling').pk, result.pk)
            with self.assertRaises(ValidationError): self.apply(self.row(), direction='bling')
        self.assertEqual(len(self.remote_calls), 1)
        BlingStockCorrection.objects.filter(pk=result.pk).update(created_at=timezone.now()-timezone.timedelta(minutes=6))
        service.acknowledge(actor=self.actor, correction_id=result.pk, reason='Valor conferido no cadastro externo')
        result.refresh_from_db()
        self.assertEqual(result.status, 'REVIEWED')

    def test_missing_duplicate_and_unit_mismatch_are_not_zero(self):
        original = self.remote
        for mode in ('missing', 'duplicate', 'unit'):
            def bad(path, **kwargs):
                result = original(path, **kwargs)
                if mode == 'missing' and path.startswith('/estoques'): result['data'] = []
                if mode == 'duplicate' and path.startswith('/produtos?'): result['data'] *= 2
                if mode == 'unit' and path == '/produtos/99': result['data']['unidade'] = 'KG'
                return result
            with patch('apps.integrations.bling.read', side_effect=bad):
                row = self.row()
                self.assertIn('error', row)
                self.assertNotIn('token', row)

    def test_preview_post_only_permissions_and_tamper(self):
        url = reverse('bling_stock_comparison')
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.actor)
        page = self.client.get(url, {'location': self.location.pk, 'deposit': 42})
        self.assertContains(page, 'Corrigir MVet usando Bling')
        token = page.context['rows'][0]['token']
        preview = self.client.post(url, {'token': token, 'field': 'price', 'direction': 'mvet', 'reason': 'Conferência'})
        self.assertContains(preview, 'Confirmar correção no MVET')
        self.assertFalse(BlingStockCorrection.objects.exists())
        response = self.client.post(url, {'action': 'confirm', 'approval': preview.context['preview']['approval']})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BlingStockCorrection.objects.get().status, 'DONE')
        response = self.client.post(url, {'action': 'confirm', 'approval': 'tampered'})
        self.assertContains(response, 'Confirmação expirada')
        self.assertEqual(BlingStockCorrection.objects.count(), 1)

    def test_no_cost_reference_and_negative_stock_blocked(self):
        other = StockBalance.objects.get(product=self.product, location=self.location)
        other.average_cost = 0
        other.save()
        self.remote_quantity = D(15)
        result = self.apply(self.row(), field='quantity')
        self.assertEqual(result.status, 'FAILED')
        self.assertIn('sem custo', result.message)
        self.remote_quantity = D(-1)
        self.assertEqual(self.apply(self.row(), field='quantity').status, 'FAILED')

    def test_adapter_allowlist_and_exact_decimal_json(self):
        for method, path, payload in [('DELETE', '/produtos/99', {}), ('PATCH', '/produtos/99', {'custo': 10}),
                                      ('POST', '/nfe', {}), ('POST', '/estoques', {'operacao': 'E'})]:
            with self.assertRaises(bling.BlingError): bling.request_json(path, method=method, payload=payload)
        self.assertEqual(bling.decimal_json({'preco': D('999999999999.99')}), '{"preco":999999999999.99}')

    def test_create_product_from_bling_with_optional_stock_and_replay(self):
        from apps.products.models import Product
        remote_id = self.product.pk
        self.product.sku = 'NEW-BLING'
        token = service.new_product_preview(actor=self.actor, remote_id='99', location=self.location, deposit='42')
        arguments = dict(actor=self.actor, token=token, name='Produto novo', price=D('9.10'), include_stock=True, cost=D('4.50'), reason='Contagem inicial conferida')
        product = service.create_product(**arguments)
        product.refresh_from_db()
        self.assertEqual((product.quantity, product.average_cost, product.fixed_sale_price), (D(7), D('4.5'), D('9.10')))
        self.assertEqual(service.create_product(**arguments).pk, product.pk)
        self.assertEqual(Product.objects.filter(sku='NEW-BLING').count(), 1)
        self.assertNotEqual(product.pk, remote_id)
        self.assertFalse(self.remote_calls)

    def test_create_without_stock_and_missing_cost_rejected(self):
        from apps.products.models import Product
        self.product.sku = 'NO-STOCK'
        token = service.new_product_preview(actor=self.actor, remote_id='99', location=self.location, deposit='42')
        args = dict(actor=self.actor, token=token, name='Novo', price=D(9), include_stock=True, cost=None, reason='Cadastro')
        with self.assertRaises(ValidationError): service.create_product(**args)
        self.assertFalse(Product.objects.filter(sku='NO-STOCK').exists())
        args['include_stock'] = False
        result = service.create_product(**args)
        self.assertEqual(result.quantity, 0)
        self.assertFalse(result.movements.exists())

    def test_catalog_creation_web_and_permissions(self):
        from apps.products.models import Product
        self.product.sku = 'CATALOG-NEW'
        url = reverse('bling_product_catalog')
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.actor)
        params = dict(location=self.location.pk, deposit=42, search='sku', q='CATALOG-NEW')
        page = self.client.get(url, params)
        self.assertContains(page, 'Cadastrar no MVet')
        params['product'] = '99'
        page = self.client.get(url, params)
        self.assertContains(page, 'Confirmar cadastro no MVet')
        token = page.context['form'].initial['token']
        response = self.client.post(url, dict(token=token, name='Novo pelo formulário', price='8.50', reason='Conferido'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.get(sku='CATALOG-NEW').fixed_sale_price, D('8.5'))
        self.assertEqual(self.client.post(url, dict(token='invalid', name='X', price='2', reason='X')).status_code, 200)


    def test_extra_decimals_are_normalized_but_invalid_values_rejected(self):
        self.remote_price = D('9.105')
        self.remote_quantity = D('7.123456')
        row = self.row()
        self.assertEqual(row['remote']['price'], '9.11')
        self.assertEqual(row['remote']['quantity'], '7.1235')
        self.assertEqual(self.apply(row).status, 'DONE')
        for invalid in (None, '', 'NaN', 'Infinity', '1e50'):
            with self.assertRaises(ValidationError): service.decimal(invalid, '.01')
        self.remote_quantity = None
        self.assertIn('error', self.row())

    def test_saved_query_filter_return_logout_and_explicit_refresh(self):
        url = reverse('bling_stock_comparison')
        self.client.force_login(self.actor)
        params = {'location': self.location.pk, 'deposit': '42', 'q': self.product.sku}
        first = self.client.get(url, params)
        self.assertEqual(len(first.context['rows']), 1)
        with patch('apps.integrations.bling.read', side_effect=AssertionError('Unexpected API call')):
            for filters in ({}, {'differences': 'on'}, {'differences': ''}):
                response = self.client.get(url, filters)
                self.assertEqual(len(response.context['rows']), 1)
                self.assertEqual(response.context['form']['q'].value(), self.product.sku)
            self.client.logout()
            self.client.force_login(self.actor)
            self.assertEqual(len(self.client.get(url).context['rows']), 1)
        self.remote_price = D('12.00')
        response = self.client.get(url, dict(params, refresh='1'), follow=True)
        self.assertEqual(response.context['rows'][0]['remote']['price'], '12.00')
        self.assertNotIn('refresh=', response.redirect_chain[-1][0])

    def test_search_sku_exact_and_only_matching_remote_products(self):
        self.client.force_login(self.actor)
        url = reverse('bling_stock_comparison')
        response = self.client.get(url, {'location': self.location.pk, 'deposit': '42', 'q': self.product.name})
        self.assertEqual(response.context['page'].paginator.count, 0)
        original = self.remote
        def unrelated(path, **kwargs):
            result = original(path, **kwargs)
            if path.startswith('/produtos?'):
                result['data'].append(dict(result['data'][0], codigo='UNRELATED', id=101))
            return result
        with patch('apps.integrations.bling.read', side_effect=unrelated):
            self.assertNotIn('error', self.row())

    def test_saved_result_after_correction_and_stale_values_still_blocked(self):
        self.client.force_login(self.actor)
        url = reverse('bling_stock_comparison')
        response = self.client.get(url, {'location': self.location.pk, 'deposit': '42'})
        token = response.context['rows'][0]['token']
        preview = self.client.post(url, {'token': token, 'field': 'price', 'direction': 'mvet', 'reason': 'Conferido'})
        self.client.post(url, {'action': 'confirm', 'approval': preview.context['preview']['approval']})
        with patch('apps.integrations.bling.read', side_effect=AssertionError('Unexpected API call')):
            response = self.client.get(url)
        row = response.context['rows'][0]
        self.assertFalse(row['price_diff'])
        self.assertEqual(row['local']['price'], '9.10')
        self.remote_quantity = D('100')
        self.assertEqual(self.apply(row, field='quantity').status, 'FAILED')

    def test_saved_snapshot_remains_valid_after_thirty_minutes(self):
        from django.core import signing
        with patch('django.core.signing.time.time', return_value=1000):
            token = self.row()['token']
        self.assertEqual(service.decode(self.actor, token)['product'], self.product.pk)
        with self.assertRaises(ValidationError): service.decode(self.actor, token + 'tampered')


    def test_difference_filter_hides_and_restores_matching_row_without_api(self):
        self.remote_price = D(service.local(self.product, self.location)['price'])
        self.remote_quantity = D(service.local(self.product, self.location)['quantity'])
        self.client.force_login(self.actor)
        url = reverse('bling_stock_comparison')
        self.client.get(url, {'location': self.location.pk, 'deposit': '42'})
        with patch('apps.integrations.bling.read', side_effect=AssertionError('Unexpected API call')):
            self.assertEqual(self.client.get(url, {'differences': 'on'}).context['rows'], [])
            self.assertEqual(len(self.client.get(url, {'differences': ''}).context['rows']), 1)


    def test_numeric_sku_order_before_pagination_and_saved_page(self):
        from apps.products.models import Product
        from .models import BlingComparisonCache
        Product.objects.filter(pk=self.product.pk).update(active=False)
        skus = [str(n) for n in range(55, 0, -1)] + ['A1']
        for sku in skus:
            Product.objects.create(sku=sku, name='Ordenação sintética', kind='SIMPLE', unit='UN')
        def compare(**kwargs):
            return [{'product': p, 'error': 'Sem vínculo externo'} for p in kwargs['products']]
        self.client.force_login(self.actor)
        url = reverse('bling_stock_comparison')
        params = {'location': self.location.pk, 'deposit': '42'}
        with patch('apps.integrations.stock_comparison.comparison', side_effect=compare):
            first = self.client.get(url, params)
            self.assertEqual([r['product']['sku'] for r in first.context['rows']],
                             [str(n) for n in range(1, 51)])
            second = self.client.get(url, dict(params, page='2'))
            self.assertEqual([r['product']['sku'] for r in second.context['rows']], ['51', '52', '53', '54', '55', 'A1'])
        cache = BlingComparisonCache.objects.get(actor=self.actor)
        cache.payload['rows'].reverse()
        cache.save()
        with patch('apps.integrations.bling.read', side_effect=AssertionError('Unexpected API call')):
            restored = self.client.get(url)
            self.assertEqual([r['product']['sku'] for r in restored.context['rows']], ['51', '52', '53', '54', '55', 'A1'])
