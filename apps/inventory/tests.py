from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal as D
from tempfile import NamedTemporaryFile
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile
from django.contrib.auth.models import User, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, connections, DatabaseError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse as url
from apps.core.models import Company, AuditLog
from apps.products.models import Product
from apps.products.services import save_product, remove_product, set_components
from .models import StockLocation, StockBalance, StockOperation, StockMovement
from .services import execute, reverse
from .importing import load_opening, read_inventory

DAY=date(2026,9,15)
class StockFixtures:
    def setUp(self):
        clock=patch('apps.inventory.services.timezone.localdate',return_value=date(2026,9,20))
        clock.start();self.addCleanup(clock.stop)
        Company.objects.create(pk=1)
        self.actor=User.objects.create_superuser('stock-admin',password='testing-only')
        self.p=Product.objects.create(sku='P1',name='Produto teste')
        self.loc=StockLocation.objects.create(name='Loja')
        self.full=StockLocation.objects.create(name='Full')
    def op(self,kind='RECEIPT',**kwargs):
        values=dict(actor=self.actor,key=uuid4(),kind=kind,date=DAY,reason='Teste operacional',product_id=self.p.pk,location_id=self.loc.pk,quantity=D('10'),cost=D('5') if kind in {'RECEIPT','OPENING','ADJUST_IN','REVALUE'} else None)
        values.update(kwargs);return execute(**values)
    def fresh(self): self.p.refresh_from_db();return self.p

@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class InventoryTests(StockFixtures,TestCase):
    def test_weighted_average_and_historical_snapshot(self):
        self.op('OPENING');sale=self.op('ISSUE',quantity=D('2'))
        snapshot=sale.movements.get().value
        self.op(quantity=D('2'),cost=D('15'))
        self.assertEqual(self.fresh().average_cost,D('7'))
        self.assertEqual(sale.movements.get().value,snapshot)
        self.assertEqual(self.p.quantity,D('10'))
    def test_last_issue_clears_rounding_residue(self):
        self.op(quantity=D('3'),cost=D('0.333333'))
        self.op('ISSUE',quantity=D('1'));self.op('ISSUE',quantity=D('2'))
        self.assertEqual(self.fresh().value,0)
    def test_insufficient_stock_rolls_back(self):
        self.op();count=StockOperation.objects.count()
        with self.assertRaises(ValidationError):self.op('ISSUE',quantity=D('11'))
        self.assertEqual(StockOperation.objects.count(),count);self.assertEqual(self.fresh().quantity,10)
    def test_local_shortage_rolls_back(self):
        self.op()
        with self.assertRaises(ValidationError):self.op('ISSUE',location_id=self.full.pk,quantity=D('1'))
        self.assertEqual(self.fresh().quantity,10)
    def test_transfer_preserves_value_and_average(self):
        self.op();self.op('TRANSFER',quantity=D('10'),target_location_id=self.full.pk)
        self.assertEqual(self.fresh().quantity,10);self.assertEqual(self.p.value,50);self.assertEqual(self.p.average_cost,5)
        self.assertEqual(StockBalance.objects.get(product=self.p,location=self.full).quantity,10)
    def test_split_preserves_total_value(self):
        target=Product.objects.create(sku='FRAC',name='Fração')
        self.op();self.op('SPLIT',quantity=D('2'),target_product_id=target.pk,target_quantity=D('50'))
        target.refresh_from_db();self.assertEqual(target.average_cost,D('0.2'));self.assertEqual(target.value+self.fresh().value,50)
    def test_kit_snapshot_reversal_ignores_new_composition(self):
        kit=Product.objects.create(sku='KIT',name='Kit teste',kind='KIT')
        self.op();set_components(actor=self.actor,kit_id=kit.pk,items=[(self.p.pk,D('2'))])
        op=self.op('KIT_ISSUE',product_id=kit.pk,quantity=D('2'))
        self.assertEqual(self.fresh().quantity,6)
        set_components(actor=self.actor,kit_id=kit.pk,items=[(self.p.pk,D('3'))])
        reverse(actor=self.actor,operation_id=op.pk,key=uuid4(),date=DAY,reason='Cancelar kit')
        self.assertEqual(self.fresh().quantity,10)
    def test_multi_component_kit_atomic_failure(self):
        kit=Product.objects.create(sku='KIT',name='Kit',kind='KIT');empty=Product.objects.create(sku='E',name='Sem saldo')
        self.op();set_components(actor=self.actor,kit_id=kit.pk,items=[(self.p.pk,D('2')),(empty.pk,D('1'))])
        with self.assertRaises(ValidationError):self.op('KIT_ISSUE',product_id=kit.pk,quantity=D('1'))
        self.assertEqual(self.fresh().quantity,10)
    def test_empty_and_nested_kit_rejected(self):
        kit=Product.objects.create(sku='KIT',name='Kit',kind='KIT')
        with self.assertRaises(ValidationError):self.op('KIT_ISSUE',product_id=kit.pk,quantity=D('1'))
        with self.assertRaises(ValidationError):set_components(actor=self.actor,kit_id=kit.pk,items=[(kit.pk,D('1'))])
    def test_adjustments_and_cost_correction(self):
        self.op();self.op('ADJUST_OUT',quantity=D('2'));self.op('ADJUST_IN',quantity=D('2'),cost=D('10'))
        self.assertEqual(self.fresh().average_cost,6)
        self.op('REVALUE',quantity=D('0'),cost=D('8'));self.assertEqual(self.fresh().value,80)
    def test_zero_opening_retains_reference_cost(self):
        self.op('OPENING',quantity=D('0'),cost=D('12'))
        self.assertEqual(self.fresh().average_cost,12);self.assertEqual(self.p.value,0)
    def test_idempotent_submission_and_payload_conflict(self):
        key=uuid4();a=self.op(key=key);b=self.op(key=key)
        self.assertEqual(a.pk,b.pk);self.assertEqual(self.fresh().quantity,10)
        with self.assertRaises(ValidationError):self.op(key=key,quantity=D('2'))
    def test_reverse_is_idempotent_and_restores_opening(self):
        op=self.op();key=uuid4()
        args=dict(actor=self.actor,operation_id=op.pk,key=key,date=DAY,reason='Correção')
        a=reverse(**args);b=reverse(**args)
        self.assertEqual(a.pk,b.pk);self.assertEqual(self.fresh().quantity,0);self.assertEqual(self.p.average_cost,0)
        with self.assertRaises(ValidationError):reverse(**{**args,'key':uuid4()})
    def test_reverse_transfer(self):
        self.op();op=self.op('TRANSFER',quantity=D('10'),target_location_id=self.full.pk)
        reverse(actor=self.actor,operation_id=op.pk,key=uuid4(),date=DAY,reason='Desfazer transferência')
        self.assertEqual(StockBalance.objects.get(product=self.p,location=self.loc).quantity,10)
        self.assertEqual(self.fresh().value,50)
    def test_reverse_with_later_activity_is_blocked(self):
        op=self.op();self.op('ISSUE',quantity=D('1'))
        with self.assertRaises(ValidationError):reverse(actor=self.actor,operation_id=op.pk,key=uuid4(),date=DAY,reason='Tentar')
    def test_reverse_chain_in_reverse_order(self):
        first=self.op();second=self.op('ISSUE',quantity=D('1'))
        for op in [second,first]:
            reverse(actor=self.actor,operation_id=op.pk,key=uuid4(),date=DAY,reason='Desfazer em ordem')
        self.assertEqual(self.fresh().quantity,0)
    def test_cutover_duplicate_opening_and_backdating(self):
        with self.assertRaises(ValidationError):self.op('OPENING',date=DAY-timedelta(days=1))
        self.op('OPENING')
        with self.assertRaises(ValidationError):self.op('OPENING')
        self.op(date=DAY+timedelta(days=1))
        with self.assertRaises(ValidationError):self.op(date=DAY)
    def test_decimal_precision_and_floats_rejected(self):
        for qty in [1.5,D('-1'),D('NaN'),D('0.00001')]:
            with self.subTest(qty=qty),self.assertRaises(ValidationError):self.op(quantity=qty)
    def test_inactive_products_and_locations_rejected(self):
        self.p.active=False;self.p.save()
        with self.assertRaises(ValidationError):self.op()
        self.p.active=True;self.p.save();self.loc.active=False;self.loc.save()
        with self.assertRaises(ValidationError):self.op()
    def test_historical_product_inactivated_unused_deleted(self):
        unused=Product.objects.create(sku='U',name='Unused');remove_product(actor=self.actor,pk=unused.pk)
        self.assertFalse(Product.objects.filter(pk=unused.pk).exists())
        self.op();remove_product(actor=self.actor,pk=self.p.pk);self.assertFalse(self.fresh().active)
    def test_unit_cannot_change_after_movement(self):
        self.op()
        with self.assertRaises(ValidationError):save_product(actor=self.actor,pk=self.p.pk,data={'unit':'KG'})
    def test_audit_contains_before_after_and_actor(self):
        op=self.op();log=AuditLog.objects.get(entity='inventory.StockMovement',entity_id=str(op.movements.get().pk))
        self.assertEqual(log.actor,self.actor);self.assertEqual(D(log.before['quantity']),0);self.assertEqual(D(log.after['quantity']),10)
    def test_ledger_model_cannot_be_edited(self):
        op=self.op()
        with self.assertRaises(ValidationError):op.save()
        with self.assertRaises(ValidationError):op.movements.get().delete()
    def test_stock_operator_cannot_read_or_submit_costs(self):
        self.op();user=User.objects.create_user('operator');user.user_permissions.add(Permission.objects.get(codename='operate_stock'))
        self.client.force_login(user)
        data=self.client.get(url('product_lookup'),{'q':'P1'}).json()['results'][0]
        self.assertNotIn('cost',data)
        for route in [url('products'),url('product_detail',args=[self.p.pk]),url('operation_detail',args=[StockOperation.objects.first().pk])]:
            response=self.client.get(route);self.assertEqual(response.status_code,200);self.assertNotContains(response,'R$')
        with self.assertRaises(PermissionDenied):self.op(actor=user)
    def test_sales_operator_read_only_catalog(self):
        user=User.objects.create_user('sales');user.user_permissions.add(Permission.objects.get(codename='operate_sales'));self.client.force_login(user)
        self.assertEqual(self.client.get(url('products')).status_code,200)
        self.assertEqual(self.client.get(url('operation_new')).status_code,403)
        self.assertEqual(self.client.post(url('product_remove',args=[self.p.pk])).status_code,403)
    def test_forms_and_templates_render(self):
        self.client.force_login(self.actor);self.op()
        kit=Product.objects.create(sku='K',name='Kit',kind='KIT')
        for route in [url('products'),url('product_new'),url('product_edit',args=[self.p.pk]),url('operation_new'),url('operations'),url('named',args=['locais']),url('components',args=[kit.pk])]:
            with self.subTest(route=route):self.assertEqual(self.client.get(route).status_code,200)
    def test_http_post_receipt_and_duplicate(self):
        self.client.force_login(self.actor);data={'key':str(uuid4()),'kind':'RECEIPT','date':DAY.isoformat(),'reason':'NF teste','product':self.p.pk,'location':self.loc.pk,'quantity':'2','cost':'3.25'}
        for _ in range(2):self.assertEqual(self.client.post(url('operation_new'),data).status_code,302)
        self.assertEqual(self.fresh().value,D('6.5'))
    def test_http_revalue_and_permission(self):
        self.client.force_login(self.actor);self.op();data={'key':str(uuid4()),'kind':'REVALUE','date':DAY.isoformat(),'reason':'Inventário','product':self.p.pk,'location':self.loc.pk,'quantity':'0','cost':'3'}
        self.assertEqual(self.client.post(url('operation_new'),data).status_code,302)
        self.assertEqual(self.fresh().value,30)
    def test_csrf_and_post_only_delete(self):
        from django.test import Client
        client=Client(enforce_csrf_checks=True);client.force_login(self.actor)
        self.assertEqual(client.post(url('operation_new'),{}).status_code,403)
        self.client.force_login(self.actor);self.assertEqual(self.client.get(url('product_remove',args=[self.p.pk])).status_code,405)
    def test_search_and_pagination(self):
        Product.objects.bulk_create([Product(sku=f'X{i}',name=f'Outros {i}') for i in range(35)])
        self.client.force_login(self.actor)
        response=self.client.get(url('products'));self.assertEqual(len(response.context['page']),36)
        self.assertEqual(self.client.get(url('products'),{'q':'P1'}).context['page'].paginator.count,1)
        self.assertLessEqual(len(self.client.get(url('product_lookup'),{'q':'Outros'}).json()['results']),20)

class ImportTests(StockFixtures,TestCase):
    def file(self,duplicate=False,invalid=False):
        f=NamedTemporaryFile(suffix='.xlsx');self.addCleanup(f.close)
        rows='<row r="3"><c r="A3"><v>825</v></c><c r="B3" t="inlineStr"><is><t>Produto</t></is></c><c r="C3"><v>15</v></c><c r="D3"><v>121.93</v></c></row>'
        if duplicate:rows+='<row r="4"><c r="A4"><v>825</v></c><c r="B4" t="inlineStr"><is><t>Produto</t></is></c><c r="C4"><v>0</v></c><c r="D4"><v>112.83</v></c></row>'
        if invalid:rows=rows.replace('<v>15</v>','<v>-1</v>')
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        with ZipFile(f.name,'w') as z:
            z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="ESTOQUE MVET" r:id="r1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><sheetData>{rows}</sheetData></worksheet>')
        return f.name
    def test_preview_never_writes(self):
        report=load_opening(actor=self.actor,path=self.file(),location_name='Inicial');self.assertFalse(report['errors']);self.assertEqual(StockOperation.objects.count(),0)
    def test_explicit_duplicate_consolidation(self):
        path=self.file(duplicate=True);_,report=read_inventory(path);self.assertTrue(report['errors'])
        rows,report=read_inventory(path,merge_duplicates=True);self.assertFalse(report['errors']);self.assertTrue(report['warnings']);self.assertEqual(rows[0]['cost'],D('121.93'));self.assertEqual(rows[0]['quantity'],15)
    def test_import_idempotent(self):
        args=dict(actor=self.actor,path=self.file(),location_name='Inicial',commit=True)
        report=load_opening(**args);self.assertEqual(report['loaded'],1)
        report=load_opening(**args);self.assertTrue(report['already_loaded']);self.assertEqual(StockOperation.objects.count(),1)
    def test_invalid_import_is_atomic(self):
        report=load_opening(actor=self.actor,path=self.file(invalid=True),location_name='Inicial',commit=True)
        self.assertTrue(report['errors']);self.assertEqual(StockOperation.objects.count(),0)
    def test_existing_sku_is_not_overwritten(self):
        Product.objects.create(sku='825',name='Existente')
        with self.assertRaises(ValidationError):load_opening(actor=self.actor,path=self.file(),location_name='Inicial',commit=True)

@skipUnless(connection.vendor=='postgresql','PostgreSQL required for concurrency and trigger verification')
class PostgreSQLInventoryTests(StockFixtures,TransactionTestCase):
    def test_concurrent_issues_do_not_oversell(self):
        self.op(quantity=D('1'))
        def issue():
            try:
                user=User.objects.get(pk=self.actor.pk)
                self.op('ISSUE',actor=user,quantity=D('1'));return 'ok'
            except ValidationError:return 'blocked'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:issue(),range(2)))
        self.assertCountEqual(results,['ok','blocked']);self.assertEqual(self.fresh().quantity,0)
    def test_concurrent_double_click_only_one_receipt(self):
        key=uuid4()
        def receipt():
            try:return self.op(actor=User.objects.get(pk=self.actor.pk),key=key).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:receipt(),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.fresh().quantity,10)
    def test_database_prevents_ledger_bulk_update_and_delete(self):
        op=self.op()
        with self.assertRaises(DatabaseError),transaction.atomic():StockOperation.objects.filter(pk=op.pk).update(reason='Alterar')
        with self.assertRaises(DatabaseError),transaction.atomic():StockMovement.objects.filter(operation=op).delete()
