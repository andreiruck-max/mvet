from django.test import TestCase
from django.core.exceptions import ValidationError
from django.urls import reverse
from apps.sales.tests import Fixture
from apps.sales.models import Sale
from apps.inventory.models import StockMovement
from apps.finance.models import FinancialTitle
from apps.core.models import AuditLog
from .models import BlingConnection
from .services import stage, approve
from .forms import ReviewForm
from .tests import payload, ISSUER


class MissingPurposeTests(Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.connection = BlingConnection.objects.create(pk=1, issuer=ISSUER)
        self.document = payload()
        self.document.pop('finalidade')
        self.document['tipoNota'] = ''
        self.document['naturezaOperacao'] = {'id': 123}
        self.document['itens'][0]['cfop'] = '6108'

    def stage(self):
        return stage(actor=self.actor, connection=self.connection, payload=self.document)

    def approve(self, row, **kwargs):
        return approve(actor=self.actor, invoice_id=row.pk, revision=row.revision,
                       data=self.data(), extra_costs=[], reviewed=True, **kwargs)

    def test_real_shape_enters_queue_without_side_effects_and_requires_review(self):
        moves = StockMovement.objects.count()
        row = self.stage()
        self.assertEqual(row.status, 'PENDING')
        self.assertEqual(row.source['purpose'], '')
        for option in ({}, {'purpose_reviewed': False}, {'purpose_reviewed': 'true'}):
            with self.assertRaises(ValidationError):
                self.approve(row, **option)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(FinancialTitle.objects.exists())
        self.assertEqual(StockMovement.objects.count(), moves)

    def test_manual_review_is_audited_without_fabricating_external_purpose(self):
        row = self.stage()
        sale = self.approve(row, purpose_reviewed=True)
        row.refresh_from_db()
        self.assertEqual(row.approved_source['purpose'], '')
        self.assertEqual(sale.cmv, 10)
        log = AuditLog.objects.get(operation='bling_approve')
        self.assertTrue(log.after['purpose_missing'])
        self.assertTrue(log.after['purpose_reviewed'])
        self.assertEqual(log.actor, self.actor)
        self.assertEqual(self.approve(row).pk, sale.pk)
        self.assertEqual(Sale.objects.count(), 1)

    def test_known_non_normal_purpose_cannot_be_overridden(self):
        for value in (2, 3, 4, 9):
            self.document['finalidade'] = value
            row = self.stage()
            self.assertEqual(row.status, 'ERROR')
            with self.assertRaises(ValidationError):
                self.approve(row, purpose_reviewed=True)

    def test_missing_purpose_does_not_bypass_status_type_or_cfop(self):
        for changes in ({'situacao': 2}, {'tipo': 0}):
            original = dict(self.document)
            self.document.update(changes)
            self.assertEqual(self.stage().status, 'ERROR')
            self.document = original
        for cfop in ('5905', '6202', '6901'):
            self.document['itens'][0]['cfop'] = cfop
            row = self.stage()
            self.assertEqual(row.status, 'ERROR')
            with self.assertRaises(ValidationError): self.approve(row, purpose_reviewed=True)

    def test_master_form_requires_explicit_purpose_confirmation(self):
        row = self.stage()
        form = ReviewForm({}, invoice=row, actor=self.actor)
        self.assertFalse(form.is_valid())
        self.assertIn('purpose_reviewed', form.errors)
        self.client.force_login(self.actor)
        response = self.client.get(reverse('bling_detail', args=[row.pk]))
        self.assertContains(response, 'Finalidade não informada pelo Bling')
        self.assertContains(response, 'id_purpose_reviewed')
        self.client.post(reverse('bling_detail', args=[row.pk]), {})
        self.assertFalse(Sale.objects.exists())

    def test_requery_recovers_old_error_and_preserves_ignored_state(self):
        row = self.stage()
        row.status = 'ERROR'; row.error = 'Somente NF autorizada, de saída e finalidade normal pode gerar venda.'
        row.save()
        updated = self.stage()
        self.assertEqual(updated.pk, row.pk)
        self.assertEqual(updated.status, 'PENDING')
        self.assertEqual(updated.error, '')
        updated.status = 'IGNORED'; updated.save()
        self.assertEqual(self.stage().status, 'IGNORED')
