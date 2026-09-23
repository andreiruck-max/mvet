from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch
from cryptography.fernet import Fernet
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.sales.models import Sale
from apps.sales.services import cancel
from apps.inventory.models import StockMovement
from apps.finance.models import FinancialTitle
from apps.core.models import AuditLog
from .models import BlingConnection, InvoiceImport
from .services import stage, approve, set_ignored, map_product
from . import bling

ISSUER = '12345678000199'  # Synthetic fixture, no company data.


def payload(**changes):
    result = {'id': 1000, 'numero': '123', 'serie': 1, 'chaveAcesso': '412609'+ISSUER+'550010000001231000000019',
        'dataEmissao': str(timezone.localdate())+' 10:00:00', 'tipo': 1, 'situacao': 5, 'finalidade': 1,
        'valorNota': '100.00', 'valorFrete': '0', 'loja': {'id': 12}, 'numeroPedidoLoja': 'EXT-1',
        'custoMedio': '999999', 'itens': [{'codigo': 'TEST-1', 'descricao': 'Produto sintético',
        'unidade': 'UN', 'quantidade': '2', 'valor': '50', 'tipo': 'P', 'cfop': '5102', 'custo': '999999'}]}
    result.update(changes); return result


class ImportTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.connection = BlingConnection.objects.create(pk=1, issuer=ISSUER)

    def staged(self, **changes):
        return stage(actor=self.actor, connection=self.connection, payload=payload(**changes))

    def approve(self, row, **changes):
        return approve(actor=self.actor, invoice_id=row.pk, revision=row.revision, data=self.data(**changes), extra_costs=[('MDR', D('2'))], reviewed=True)

    def test_preview_has_no_effect_and_costs_are_not_retained(self):
        moves = StockMovement.objects.count(); row = self.staged()
        self.assertEqual(row.status, 'PENDING'); self.assertEqual(StockMovement.objects.count(), moves)
        self.assertFalse(Sale.objects.exists()); self.assertFalse(FinancialTitle.objects.exists())
        self.assertNotIn('999999', str(row.source)); self.assertEqual(row.source['number'], '123')

    def test_approve_uses_local_cost_at_confirmation_and_chosen_stock(self):
        row = self.staged(); self.receive(self.product, D('10'), D('15'))
        sale = self.approve(row)
        self.assertEqual(sale.cmv, D('20')); self.assertEqual(sale.invoice_number, '123')
        self.assertEqual(sale.source, 'bling'); self.assertEqual(sale.external_id, '1000')
        self.assertEqual(sale.extra_costs_total, D('2')); self.assertEqual(sale.location, self.location)
        self.product.refresh_from_db(); self.assertEqual(self.product.quantity, 18)
        self.assertEqual(FinancialTitle.objects.count(), 1)

    def test_double_approval_and_cancel_repoll_never_reactivate(self):
        row = self.staged(); sale = self.approve(row)
        self.assertEqual(self.approve(row).pk, sale.pk)
        with patch('apps.integrations.bling.request_json') as remote:
            cancel(actor=self.actor, sale_id=sale.pk, reason='Cancelamento local')
            remote.assert_not_called()
        self.staged(); row.refresh_from_db(); self.assertEqual(row.sale.status, 'CANCELLED')
        self.approve(row); self.assertEqual(Sale.objects.count(), 1)
        self.product.refresh_from_db(); self.assertEqual(self.product.quantity, 10)

    def test_external_cancel_only_flags_divergence(self):
        row = self.staged(); sale = self.approve(row)
        self.staged(situacao=2); row.refresh_from_db(); sale.refresh_from_db()
        self.assertTrue(row.discrepancy); self.assertEqual(sale.status, 'CONFIRMED')
        self.assertEqual(sale.fees, D('3')); self.assertEqual(sale.extra_costs_total, D('2'))
        self.assertEqual(row.approved_source['status'], '5')
        self.assertEqual(row.source['status'], '2')

    def test_ignored_stays_ignored_until_explicit_reopen(self):
        row = self.staged()
        set_ignored(actor=self.actor, invoice_id=row.pk, revision=row.revision, ignored=True, reason='Não incluir')
        self.staged(); row.refresh_from_db(); self.assertEqual(row.status, 'IGNORED')
        with self.assertRaises(ValidationError): self.approve(row)
        set_ignored(actor=self.actor, invoice_id=row.pk, revision=row.revision, ignored=False, reason='Conferir novamente')
        row.refresh_from_db(); self.assertEqual(row.status, 'PENDING')

    def test_stale_revision_and_incomplete_confirmation_block(self):
        row = self.staged(); self.staged(valorNota='90')
        with self.assertRaises(ValidationError): self.approve(row)
        row.refresh_from_db()
        with self.assertRaises(ValidationError):
            approve(actor=self.actor, invoice_id=row.pk, revision=row.revision, data=self.data(), extra_costs=[], reviewed=False)

    def test_shortage_rolls_back_sale_and_import(self):
        data = payload(); data['itens'][0]['quantidade'] = '100'
        row = stage(actor=self.actor, connection=self.connection, payload=data)
        with self.assertRaises(ValidationError): self.approve(row)
        row.refresh_from_db(); self.assertEqual(row.status, 'PENDING'); self.assertIsNone(row.sale_id)
        self.assertFalse(Sale.objects.exists()); self.assertFalse(FinancialTitle.objects.exists())

    def test_manual_duplicate_rejected_without_stock_effect(self):
        self.draft(invoice_number='123', invoice_series='1')
        row = self.staged()
        with self.assertRaises(ValidationError): self.approve(row)
        self.product.refresh_from_db(); self.assertEqual(self.product.quantity, 10)

    def test_external_alias_requires_permission_and_matching_unit(self):
        data = payload(); data['itens'][0]['codigo'] = 'EXTERNAL-LISTING'
        row = stage(actor=self.actor, connection=self.connection, payload=data)
        with self.assertRaises(ValidationError): self.approve(row)
        with self.assertRaises(PermissionDenied):
            map_product(actor=self.operator, invoice_id=row.pk, revision=row.revision, code='EXTERNAL-LISTING', unit='UN', product=self.product)
        map_product(actor=self.actor, invoice_id=row.pk, revision=row.revision, code='EXTERNAL-LISTING', unit='UN', product=self.product)
        row.refresh_from_db(); self.assertEqual(self.approve(row).cmv, D('10'))

    def test_unit_abbreviation_exact_sku_preserves_source_and_quantity(self):
        data = payload(); data['itens'][0]['unidade'] = 'UNID'
        row = stage(actor=self.actor, connection=self.connection, payload=data)
        original = deepcopy(row.source)
        sale = self.approve(row)
        self.assertEqual(sale.cmv, D('10'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 8)
        self.assertEqual(self.product.unit, 'UN')
        row.refresh_from_db()
        self.assertEqual(row.source, original)
        self.assertEqual(row.approved_source, original)

    def test_unit_abbreviation_manual_alias_and_next_invoice(self):
        from .services import resolve
        from .models import ProductAlias
        data = payload(); data['itens'][0].update(codigo='EXT-UNIT', unidade='UNID')
        row = stage(actor=self.actor, connection=self.connection, payload=data)
        self.assertIsNone(resolve(self.connection, row.source['items'][0]))
        map_product(actor=self.actor, invoice_id=row.pk, revision=row.revision,
                    code='EXT-UNIT', unit='UNID', product=self.product)
        self.assertEqual(ProductAlias.objects.get(code='EXT-UNIT').unit, 'UNID')
        self.assertEqual(resolve(self.connection, row.source['items'][0]), self.product)
        row.refresh_from_db()
        self.assertEqual(self.approve(row).cmv, D('10'))
        self.assertEqual(resolve(self.connection, {'code': 'EXT-UNIT', 'unit': 'UNID'}), self.product)

    def test_unit_equivalence_is_symmetric_and_rejects_other_measures(self):
        from .services import compatible_units, resolve
        self.assertTrue(compatible_units(' unid ', 'un'))
        self.assertTrue(compatible_units('KG', 'KG'))
        for unit in ['KG', 'G', 'L', 'CX', 'PCT', '', 'UNIDADE']:
            self.assertFalse(compatible_units('UN', unit))
            self.assertIsNone(resolve(self.connection, {'code': self.product.sku, 'unit': unit}))
        self.product.active = False; self.product.save()
        self.assertIsNone(resolve(self.connection, {'code': self.product.sku, 'unit': 'UNID'}))

    def test_unit_mismatch_blocks_even_exact_sku(self):
        data = payload(); data['itens'][0]['unidade'] = 'KG'
        row = stage(actor=self.actor, connection=self.connection, payload=data)
        with self.assertRaises(ValidationError): self.approve(row)
        with self.assertRaises(ValidationError):
            map_product(actor=self.actor, invoice_id=row.pk, revision=row.revision, code='TEST-1', unit='KG', product=self.product)

    def test_non_sales_and_foreign_issuer_stay_blocked(self):
        for changes in [{'tipo': 0}, {'finalidade': 4}, {'situacao': 2}, {'chaveAcesso': '0'*44}]:
            row = self.staged(**changes)
            self.assertEqual(row.status, 'ERROR')
            with self.assertRaises(ValidationError): self.approve(row)
        data = payload(); data['itens'][0]['cfop'] = '5905'
        row = stage(actor=self.actor, connection=self.connection, payload=data)
        self.assertEqual(row.status, 'ERROR')

    def test_permissions_in_services_and_urls_and_no_cost_leak(self):
        row = self.staged()
        with self.assertRaises(PermissionDenied):
            approve(actor=self.operator, invoice_id=row.pk, revision=row.revision, data=self.data(), extra_costs=[], reviewed=True)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('bling_queue')).status_code, 403)
        self.assertEqual(self.client.get(reverse('bling_detail', args=[row.pk])).status_code, 403)
        self.operator.user_permissions.add(Permission.objects.get(codename='review_bling'))
        response = self.client.get(reverse('bling_detail', args=[row.pk])); self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '999999'); self.assertNotContains(response, 'Conferir e confirmar venda')
        self.assertEqual(self.client.post(reverse('bling_detail', args=[row.pk]), {}).status_code, 403)
        self.assertEqual(self.client.get(reverse('bling_connection')).status_code, 403)

    def test_csrf_and_post_only_on_mutations(self):
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse('bling_connect')).status_code, 405)
        client = Client(enforce_csrf_checks=True); client.force_login(self.actor)
        self.assertEqual(client.post(reverse('bling_query'), {}).status_code, 403)

    def test_missing_deductions_are_not_silently_zero(self):
        from .forms import ReviewForm
        row = self.staged()
        form = ReviewForm({}, invoice=row)
        self.assertFalse(form.is_valid())
        for field in ['discount', 'fees', 'difal', 'commission', 'shipping_paid', 'other_costs']:
            self.assertIn(field, form.errors)


@override_settings(BLING_TOKEN_KEY=Fernet.generate_key().decode(), BLING_CLIENT_ID='synthetic-id', BLING_CLIENT_SECRET='synthetic-secret',
                   BLING_REDIRECT_URI='http://testserver/integracoes/bling/retorno/', BLING_ISSUER_CNPJ=ISSUER)
class AdapterTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.connection = BlingConnection.objects.create(pk=1, issuer=ISSUER)
        bling.store_tokens(self.connection, {'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh', 'expires_in': 3600})

    def test_encryption_and_refresh_failure_does_not_log_secret(self):
        self.assertNotIn('synthetic-access', self.connection.tokens)
        self.connection.expires_at = timezone.now() - timedelta(seconds=1); self.connection.save()
        with patch.object(bling, 'request_json', side_effect=[{'access_token': 'rotated', 'refresh_token': 'rotated-refresh', 'expires_in': 3600}, bling.BlingError('Falha sintética')]):
            with self.assertRaises(bling.BlingError): bling.read('/nfe/1000')
        self.connection.refresh_from_db()
        self.assertIn('rotated-refresh', bling.cipher().decrypt(self.connection.tokens.encode()).decode())
        self.assertNotIn('synthetic-secret', str(list(AuditLog.objects.values())))

    def test_page_reads_details_and_safe_repeat(self):
        for _ in range(2):
            with patch.object(bling, 'read', side_effect=[{'data': [{'id': 1000}]}, {'data': payload()}]):
                run = bling.sync_page(actor=self.actor, start=timezone.localdate(), end=timezone.localdate())
            self.assertEqual(run.processed, 1); self.assertEqual(run.errors, 0); self.assertFalse(run.has_more)
        self.assertEqual(InvoiceImport.objects.count(), 1); self.assertFalse(Sale.objects.exists())

    def test_page_failure_is_recorded_and_does_not_create_sales(self):
        with patch.object(bling, 'read', side_effect=bling.BlingError('Limite atingido')):
            run = bling.sync_page(actor=self.actor, start=timezone.localdate(), end=timezone.localdate())
        self.assertEqual(run.errors, 1); self.assertIn('Limite', run.message); self.assertFalse(Sale.objects.exists())

    def test_oauth_rejects_missing_wrong_expired_and_replayed_state(self):
        self.client.force_login(self.actor)
        with patch.object(bling, 'authorize') as auth:
            self.client.get(reverse('bling_callback'), {'code': 'hidden', 'state': 'wrong'})
            auth.assert_not_called()
            response = self.client.post(reverse('bling_connect'))
            self.assertEqual(response.status_code, 302)
            state = self.client.session['bling_oauth']['state']
            self.client.get(reverse('bling_callback'), {'code': 'hidden', 'state': state})
            auth.assert_called_once()
            self.client.get(reverse('bling_callback'), {'code': 'hidden', 'state': state})
            auth.assert_called_once()

    def test_adapter_rejects_remote_writes_and_arbitrary_paths(self):
        for path in ['/nfe/1000/cancelar', 'https://example.com/', '/produtos']:
            with self.assertRaises(bling.BlingError): bling.request_json(path, form={'operation': 'write'})
            with self.assertRaises(bling.BlingError): bling.request_json(path)

    def test_disconnect_keeps_pending_notes(self):
        stage(actor=self.actor, connection=self.connection, payload=payload())
        bling.disconnect(actor=self.actor); self.connection.refresh_from_db()
        self.assertEqual(self.connection.tokens, ''); self.assertEqual(InvoiceImport.objects.count(), 1)

from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection as db_connection, connections, transaction, DatabaseError, close_old_connections
from django.test import TransactionTestCase


@skipUnless(db_connection.vendor == 'postgresql', 'PostgreSQL locking/history gate')
class ImportPostgresTests(Fixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.connection = BlingConnection.objects.create(pk=1, issuer=ISSUER)
        self.row = stage(actor=self.actor, connection=self.connection, payload=payload())

    def test_concurrent_approval_creates_one_sale_and_one_debit(self):
        data = self.data(); actor_id = self.actor.pk; pk = self.row.pk; revision = self.row.revision
        def worker():
            close_old_connections()
            try:
                actor = User.objects.get(pk=actor_id)
                return approve(actor=actor, invoice_id=pk, revision=revision, data=data, extra_costs=[], reviewed=True).pk
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(results[0], results[1]); self.assertEqual(Sale.objects.count(), 1)
        self.product.refresh_from_db(); self.assertEqual(self.product.quantity, 8)
        self.assertEqual(FinancialTitle.objects.count(), 1)

    def test_import_identity_and_approved_snapshot_are_protected_in_database(self):
        approve(actor=self.actor, invoice_id=self.row.pk, revision=self.row.revision, data=self.data(), extra_costs=[], reviewed=True)
        for values in [{'external_id': 'changed'}, {'approved_source': {}}, {'sale_id': None, 'status': 'PENDING'}]:
            with self.assertRaises(DatabaseError), transaction.atomic():
                InvoiceImport.objects.filter(pk=self.row.pk).update(**values)
        with self.assertRaises(DatabaseError), transaction.atomic():
            InvoiceImport.objects.filter(pk=self.row.pk).delete()
