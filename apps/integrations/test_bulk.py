from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from apps.sales.tests import Fixture
from apps.sales.models import Sale
from apps.inventory.models import StockMovement
from apps.finance.models import FinancialTitle
from .models import BlingConnection, InvoiceImport, PurchaseInvoiceImport
from .tests import payload, ISSUER
from .test_purchase_import import incoming
from . import services, purchase_services, bulk


class BulkTests(Fixture,TestCase):
    def setUp(self):
        super().setUp();self.connection=BlingConnection.objects.create(pk=1,issuer=ISSUER)
        self.sale=services.stage(actor=self.actor,connection=self.connection,payload=payload())
        self.purchase=purchase_services.stage(actor=self.actor,connection=self.connection,payload=incoming())
    def apply(self,kind,obj,action='ignore',**changes):
        return bulk.apply(actor=self.actor,kind=kind,selection=bulk.token(self.actor,kind,[(obj.pk,obj.revision)]),action=action,reason='Teste',changes=changes)
    def test_ignore_reopen_both_queues_refresh_preserves_no_side_effects(self):
        before=StockMovement.objects.count()
        for kind,obj in [('SALE',self.sale),('PURCHASE',self.purchase)]:
            self.assertEqual(self.apply(kind,obj),1)
        self.sale=services.stage(actor=self.actor,connection=self.connection,payload=payload())
        self.purchase=purchase_services.stage(actor=self.actor,connection=self.connection,payload=incoming())
        self.assertEqual(self.sale.status,'IGNORED');self.assertTrue(self.purchase.rejected)
        for kind,obj in [('SALE',self.sale),('PURCHASE',self.purchase)]:self.apply(kind,obj,'reopen')
        self.sale.refresh_from_db();self.purchase.refresh_from_db()
        self.assertEqual(self.sale.status,'PENDING');self.assertFalse(self.purchase.rejected)
        self.assertEqual(StockMovement.objects.count(),before);self.assertFalse(Sale.objects.exists());self.assertFalse(FinancialTitle.objects.exists())
    def test_overrides_prefill_and_survive_external_refresh(self):
        self.apply('SALE',self.sale,'edit',location=self.location.pk,channel=self.channel.pk)
        self.apply('PURCHASE',self.purchase,'edit',location=self.location.pk,acquisition_kind='BONUS')
        self.sale=services.stage(actor=self.actor,connection=self.connection,payload=payload())
        self.purchase=purchase_services.stage(actor=self.actor,connection=self.connection,payload=incoming())
        self.client.force_login(self.actor)
        response=self.client.get(reverse('bling_detail',args=[self.sale.pk]))
        self.assertEqual(response.context['form'].initial['channel'],self.channel.pk)
        response=self.client.get(reverse('bling_purchase_detail',args=[self.purchase.pk]))
        self.assertEqual(response.context['form'].initial['acquisition_kind'],'BONUS')
    def test_stale_selection_atomic_no_partial_changes(self):
        second=InvoiceImport.objects.create(connection=self.connection,external_id='2000',number='999',fingerprint='synthetic')
        selection=bulk.token(self.actor,'SALE',[(self.sale.pk,self.sale.revision),(second.pk,second.revision)])
        InvoiceImport.objects.filter(pk=second.pk).update(revision=2)
        with self.assertRaises(ValidationError):bulk.apply(actor=self.actor,kind='SALE',selection=selection,action='ignore',reason='Teste',changes={})
        self.sale.refresh_from_db();self.assertEqual(self.sale.status,'PENDING')
    def test_scope_all_is_signed_snapshot_not_new_matching_rows(self):
        self.client.force_login(self.actor)
        response=self.client.get(reverse('bling_queue'))
        token=response.context['bulk_all']
        second=InvoiceImport.objects.create(connection=self.connection,external_id='2000',number='999',fingerprint='synthetic')
        self.assertEqual(bulk.apply(actor=self.actor,kind='SALE',selection=token,action='ignore',reason='Teste',changes={}),1)
        second.refresh_from_db();self.assertEqual(second.status,'PENDING')
    def test_preview_csrf_post_only_and_permissions(self):
        url=reverse('bling_bulk',args=['SALE']);selection=bulk.token(self.actor,'SALE',[(self.sale.pk,self.sale.revision)])
        self.client.force_login(self.operator);self.assertEqual(self.client.post(url,{'selection':selection}).status_code,403)
        with self.assertRaises(PermissionDenied):bulk.apply(actor=self.operator,kind='SALE',selection=selection,action='ignore',reason='X',changes={})
        self.client.force_login(self.actor);self.assertEqual(self.client.get(url).status_code,405)
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.actor)
        self.assertEqual(secure.post(url,{'selection':selection}).status_code,403)
        data=dict(selection=selection,action='ignore',reason='Organizar',preview='1')
        response=self.client.post(url,data);self.assertContains(response,'Aplicar nas 1 notas')
        self.sale.refresh_from_db();self.assertEqual(self.sale.status,'PENDING')
        data.pop('preview');data['apply']='1';self.assertEqual(self.client.post(url,data).status_code,302)
        self.sale.refresh_from_db();self.assertEqual(self.sale.status,'IGNORED')
    def test_cannot_inject_arbitrary_review_fields_or_cross_user_token(self):
        with self.assertRaises(ValidationError):bulk.decode(self.operator,'SALE',bulk.token(self.actor,'SALE',[(self.sale.pk,1)]))
        with self.assertRaises(ValidationError):self.apply('SALE',self.sale,'edit',location=99999)
        with self.assertRaises(ValidationError):self.apply('SALE',self.sale,'edit',products_amount='999')
