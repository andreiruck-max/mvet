import io
import json
from datetime import timedelta
from decimal import Decimal as D
from zipfile import ZipFile
from xml.sax.saxutils import escape
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.sales.tests import Fixture
from apps.products.models import Product
from .models import StockLocation, StockBalance, StockMovement, InventoryReconciliation
from .spreadsheet import template_xlsx, snapshot_from_xlsx, read_xlsx
from .reconciliation import reconcile


def workbook(rows, formula=False):
    source = ZipFile(io.BytesIO(template_xlsx()))
    out = io.BytesIO()
    data = []
    for number, row in enumerate(rows, 1):
        cells = ''.join(f'<c r="{chr(65+i)}{number}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>' for i,v in enumerate(row))
        data.append(f'<row r="{number}">{cells}</row>')
    sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(data) + '</sheetData></worksheet>'
    if formula:
        sheet = sheet.replace('<is>', '<f>1+1</f><is>', 1)
    with ZipFile(out, 'w') as dest:
        for name in source.namelist():
            dest.writestr(name, sheet if name == 'xl/worksheets/sheet1.xml' else source.read(name))
    return out.getvalue()


class SpreadsheetTests(Fixture, TestCase):
    def sheet(self, qty='7', cost='8', extra=None):
        rows = [['SKU','Produto','Quantidade','Custo médio','Unidade'],[self.product.sku,'Nome externo',qty,cost,'CX']]
        if extra:
            rows.append(extra)
        return workbook(rows)

    def apply(self, raw):
        preview = reconcile(actor=self.actor, raw=raw)
        return reconcile(actor=self.actor, raw=raw, commit=True, expected_revision=preview['revision'])

    def test_replace_current_new_product_cmv_and_repeat(self):
        sale = self.confirmed(); cmv = sale.cmv
        raw = snapshot_from_xlsx(self.sheet(extra=['NEW','Produto novo','2','12,35','KG']), location=self.location)
        report = self.apply(raw)
        self.product.refresh_from_db(); sale.refresh_from_db()
        self.assertEqual((self.product.quantity,self.product.value,self.product.average_cost),(7,56,8))
        self.assertEqual((self.product.name,self.product.unit),('Produto teste','UN'))
        self.assertEqual((Product.objects.get(sku='NEW').quantity,Product.objects.get(sku='NEW').unit),(2,'KG'))
        self.assertEqual(sale.cmv,cmv)
        count = StockMovement.objects.count()
        self.assertTrue(self.apply(raw)['already_applied'])
        self.assertEqual(StockMovement.objects.count(),count)
        # Revised position in the same day is supported, without adding the prior 7 units.
        self.apply(snapshot_from_xlsx(self.sheet('3','9'),location=self.location))
        self.product.refresh_from_db()
        self.assertEqual((self.product.quantity,self.product.value),(3,27))
        self.assertEqual(InventoryReconciliation.objects.count(),2)

    def test_multi_depot_and_explicit_omissions(self):
        full = StockLocation.objects.create(name='Full ML')
        other = Product.objects.create(sku='OMIT',name='Fora da lista')
        self.receive(other,D(2),D(5))
        data = workbook([['SKU','Quantidade','Custo médio','Depósito'],[self.product.sku,7,8,self.location.name],[self.product.sku,4,12,full.name]])
        raw = snapshot_from_xlsx(data)
        self.apply(raw)
        other.refresh_from_db(); self.product.refresh_from_db()
        self.assertEqual(other.quantity,2)
        self.assertEqual((self.product.quantity,self.product.value),(11,104))
        self.apply(snapshot_from_xlsx(self.sheet(),location=self.location,complete=True))
        other.refresh_from_db()
        self.assertEqual(other.quantity,0)
        self.assertEqual(StockBalance.objects.get(product=self.product,location=full).quantity,4)

    def test_historical_preserves_later_movements_and_blocks_ambiguous_reconciliation(self):
        day = timezone.localdate()-timedelta(days=1)
        raw = snapshot_from_xlsx(self.sheet(),location=self.location,mode='historical',base_date=day)
        self.apply(raw)
        self.product.refresh_from_db()
        self.assertEqual((self.product.quantity,self.product.value),(17,106))
        with self.assertRaises(ValidationError):
            self.apply(snapshot_from_xlsx(self.sheet('8'),location=self.location,mode='historical',base_date=day))
        full=StockLocation.objects.create(name='Full ML')
        # Same date, independent depot, no global date uniqueness restriction.
        self.apply(snapshot_from_xlsx(self.sheet(),location=full,mode='historical',base_date=day))
        self.assertEqual(StockBalance.objects.get(product=self.product,location=full).quantity,7)

    def test_invalid_rows_formula_duplicate_no_writes(self):
        before = StockMovement.objects.count()
        for raw in [self.sheet(extra=[self.product.sku,'Duplicado',1,2,'UN']),
                    self.sheet(cost='NaN'),self.sheet(qty='-1'),self.sheet(qty='0.12345'),
                    workbook([['SKU','Quantidade','Custo médio'],['NEW',1,3]]),
                    workbook([['SKU','Quantidade','Custo médio'],['P',1,3]],formula=True),
                    workbook([['SKU','Quantidade','Custo médio','Valor total'],['P',1,3,999]])]:
            with self.assertRaises(ValidationError):
                snapshot_from_xlsx(raw,location=self.location)
        self.assertEqual(StockMovement.objects.count(),before)
        self.assertFalse(InventoryReconciliation.objects.exists())

    def test_locale_precision_location_mismatch_and_headers(self):
        raw=snapshot_from_xlsx(self.sheet(qty='1.234,5',cost='10,1234567'),location=self.location)
        row=json.loads(raw)['locations'][0]['items'][0]
        self.assertEqual(D(row['quantity']),D('1234.5'))
        self.assertEqual(D(row['cost']),D('10.123457'))
        self.assertEqual(read_xlsx(template_xlsx())[0][1][:3],['SKU','Produto','Quantidade'])
        with self.assertRaises(ValidationError):snapshot_from_xlsx(template_xlsx(),location=self.location,complete=True)
        with self.assertRaises(ValidationError):snapshot_from_xlsx(self.sheet())
        full=StockLocation.objects.create(name='Full')
        with self.assertRaises(ValidationError):
            snapshot_from_xlsx(workbook([['SKU','Quantidade','Custo médio','Depósito'],[self.product.sku,1,2,full.name]]),location=self.location)

    def test_master_upload_preview_confirm_and_template(self):
        url=reverse('inventory_reconcile')
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('inventory_template')).status_code,403)
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(reverse('inventory_template')).status_code,200)
        response=self.client.post(url,{'file':SimpleUploadedFile('stock.xlsx',self.sheet()),'location':self.location.pk,'mode':'current'})
        self.assertContains(response,'Aplicar conciliação no MVet')
        self.assertEqual(InventoryReconciliation.objects.count(),0)
        response=self.client.post(url,{'action':'apply','token':response.context['token']})
        self.assertEqual(response.status_code,200)
        self.product.refresh_from_db();self.assertEqual(self.product.quantity,7)
        response=self.client.post(url,{'file':SimpleUploadedFile('stock.xlsx',self.sheet()),'location':self.location.pk,'mode':'historical'})
        self.assertContains(response,'Informe a data-base.')

    def test_cached_numeric_formula_uses_saved_value_only(self):
        raw=self.sheet()
        source=ZipFile(io.BytesIO(raw));out=io.BytesIO()
        with ZipFile(out,'w') as dest:
            for name in source.namelist():
                data=source.read(name)
                if name=='xl/worksheets/sheet1.xml':
                    data=data.replace(b'<c r="C2" t="inlineStr"><is><t>7</t></is></c>',b'<c r="C2"><f>SUM(3,4)</f><v>7</v></c>')
                dest.writestr(name,data)
        payload=json.loads(snapshot_from_xlsx(out.getvalue(),location=self.location))
        self.assertEqual(D(payload['locations'][0]['items'][0]['quantity']),D(7))
