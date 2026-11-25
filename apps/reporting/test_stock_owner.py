from decimal import Decimal as D
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from django.contrib.auth.models import Permission, User
from django.core import signing
from django.test import TestCase
from django.urls import reverse
from apps.core.models import Company
from apps.inventory.models import StockBalance, StockOperation, StockMovement
from apps.inventory.tests import StockFixtures, DAY
from apps.integrations.stock_comparison import local
from apps.products.models import Product
from . import selectors, drilldown, pdf_layout
from .files import NS


class StockOwnerConsumerTests(StockFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.original=self.op().movements.get()
        Company.objects.filter(pk=1).update(default_stock_location=self.loc)
        Company.objects.get_or_create(pk=2,defaults={'active':False})
        StockBalance.objects.create(company_id=2,product=self.p,location=self.loc,
            quantity=D('100'),value=D('9900'),average_cost=D('99'))
        Product.objects.filter(pk=self.p.pk).update(quantity=D('110'),value=D('9950'))
        other=StockOperation.objects.create(company_id=2,actor=self.actor,date=DAY,
            kind='RECEIPT',key=uuid4(),reason='Projeção secundária sintética',fingerprint='owner-consumer')
        values={f.attname:getattr(self.original,f.attname) for f in StockMovement._meta.concrete_fields if not f.primary_key}
        values.update(company_id=2,operation_id=other.pk,cost_variance=D('999'))
        StockMovement.objects.create(**values)
        self.period={'start':DAY,'end':DAY}
        self.client.force_login(self.actor)

    def test_local_bling_snapshot_ignores_secondary_stock_and_revision(self):
        snapshot=local(self.p,self.loc)
        self.assertEqual(D(snapshot['quantity']),D('10'))
        self.assertEqual(D(snapshot['price']),D('6.75'))
        self.assertEqual(snapshot['last'],self.original.pk)

    def test_secondary_variance_does_not_enter_primary_dre_or_sources(self):
        result=selectors.dre(self.period)
        self.assertEqual(result['expenses']['OPERATING'],D('0'))
        token=signing.dumps({'kind':'inventory','label':'Estoque'},salt=drilldown.SALT)
        _, rows, total=drilldown.sources(token,self.period)
        self.assertEqual(rows,[])
        self.assertEqual(total,D('0'))

    def test_dashboard_stock_value_is_owned_position(self):
        response=self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['stock'],D('50'))

    def test_xlsx_main_and_depot_sheet_only_contain_this_owners_booked_position(self):
        other = Product.objects.create(sku='AG', name='SKU compartilhado sem saldo próprio')
        StockBalance.objects.create(company_id=2, product=other, location=self.loc,
            quantity=23, value=460, average_cost=20)
        self.op(location_id=self.full.pk, quantity=D('3'), cost=D('26'))
        reader = User.objects.create_user('export-qty-only')
        reader.user_permissions.add(*Permission.objects.filter(codename__in=['view_stock', 'export_stock']))
        for user, location, expected_qty, expected_cost in [
            (self.actor, self.loc, 10, 5), (self.actor, self.full, 3, 26), (reader, self.loc, 10, None),
        ]:
            with self.subTest(user=user.username, location=location.name):
                self.client.force_login(user)
                response = self.client.get(reverse('report_export', args=['stock', 'xlsx']),
                                           {'location': location.pk, 'positive': '0'})
                self.assertEqual(response.status_code, 200)
                with ZipFile(BytesIO(response.content)) as book:
                    def records(sheet):
                        xml = ET.fromstring(book.read(f'xl/worksheets/sheet{sheet}.xml'))
                        def value(cell):
                            if cell.get('t') == 'inlineStr':
                                return cell.findtext(f'{{{NS}}}is/{{{NS}}}t')
                            raw = cell.findtext(f'{{{NS}}}v')
                            return D(raw) if raw is not None else None
                        return [[value(cell) for cell in row] for row in xml.findall(f'.//{{{NS}}}row')]
                    main, local = records(1), records(2)
                by_sku = {r[0]: r for r in main if r[0] in (self.p.sku, other.sku)}
                self.assertEqual(by_sku[self.p.sku][2], expected_qty)
                self.assertEqual(by_sku[other.sku][2], 0)
                self.assertEqual('CUSTO' in main[1], expected_cost is not None)
                if expected_cost is not None:
                    self.assertEqual(by_sku[self.p.sku][3:5], [expected_cost, expected_qty * expected_cost])
                self.assertEqual(local[3:], [[self.p.sku, self.p.name, str(location), expected_qty]])

    def test_pdf_depot_detail_preserves_real_zero_and_does_not_show_foreign_stock(self):
        # Close only the primary position; the other company still owns 100 units.
        self.op('ISSUE')
        with patch.object(pdf_layout, 'dataset_table', wraps=pdf_layout.dataset_table) as rendered:
            response = self.client.get(reverse('report_export', args=['stock', 'pdf']),
                                       {'location': self.loc.pk, 'positive': '0'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF-'))
        details = [call.args[0].rows for call in rendered.call_args_list if call.args[0].title == 'Estoque por local']
        self.assertEqual(details, [[[self.p.sku, self.p.name, str(self.loc), 0]]])
