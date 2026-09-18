from datetime import timedelta
from decimal import Decimal as D
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from django.contrib.auth.models import User, Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from apps.accounts.models import AccessPolicy
from apps.core.models import AuditLog
from apps.sales import services
from .tests import ReportingFixture
from .datasets import build, Dataset
from .files import xlsx, pdf, NS


class ExportTests(ReportingFixture, TestCase):
    def url(self,kind,fmt='xlsx'):
        return reverse('report_export',args=[kind,fmt])

    def xml(self,data,number=1):
        with ZipFile(BytesIO(data)) as book:
            return ET.fromstring(book.read(f'xl/worksheets/sheet{number}.xml'))

    def test_all_existing_reports_export_both_formats_with_real_rows(self):
        self.confirmed();self.expense();self.purchase();self.client.force_login(self.actor)
        for kind in ['sales','stock','purchases','payables','cash','titles','expenses','dre','dashboard']:
            for fmt in ['xlsx','pdf']:
                with self.subTest(kind=kind,fmt=fmt):
                    r=self.client.get(self.url(kind,fmt),self.period)
                    self.assertEqual(r.status_code,200)
                    self.assertIn('attachment',r['Content-Disposition'])
                    self.assertIn('no-store',r['Cache-Control'])
                    if fmt=='xlsx':self.assertIsNotNone(self.xml(r.content))
                    else:self.assertTrue(r.content.startswith(b'%PDF-'))
        self.assertEqual(AuditLog.objects.filter(operation='export_report').count(),18)

    def test_revenue_permission_never_implies_margins_costs_or_exports(self):
        self.confirmed();user=User.objects.create_user('revenue-reader')
        user.user_permissions.add(Permission.objects.get(codename='view_dashboard'))
        self.client.force_login(user)
        r=self.client.get(reverse('dashboard_api'),self.period)
        self.assertEqual(r.status_code,200)
        self.assertEqual(D(r.json()['sales']['revenue']),95)
        for key in ['cmv','contribution','margin']:
            self.assertNotIn(key,r.json()['sales']);self.assertNotIn(key,r.json()['channels'][0])
        self.assertEqual(self.client.get(self.url('dashboard'),self.period).status_code,403)
        self.assertEqual(self.client.get(reverse('sales_sheet'),self.period).status_code,403)
        user.user_permissions.add(Permission.objects.get(codename='export_dashboard'))
        r=self.client.get(self.url('dashboard'),self.period);self.assertEqual(r.status_code,200)
        with ZipFile(BytesIO(r.content)) as z:
            xml=''.join(z.read(n).decode() for n in z.namelist() if '/worksheets/' in n)
        self.assertNotIn('CMV',xml);self.assertNotIn('contribution',xml);self.assertNotIn('Margem',xml)

    def test_cost_and_margin_columns_independent_and_no_hidden_sheet_leak(self):
        self.confirmed();user=User.objects.create_user('sales-reader')
        user.user_permissions.add(*Permission.objects.filter(codename__in=['view_sales_report','export_sales']))
        self.client.force_login(user)
        for cost,margin in [(False,False),(True,False),(False,True),(True,True)]:
            AccessPolicy.objects.update_or_create(user=user,defaults={'rules':{'core.view_costs':cost,'core.view_margins':margin}})
            r=self.client.get(self.url('sales'),self.period);self.assertEqual(r.status_code,200)
            root=self.xml(r.content)
            headers=[n.text for n in root.findall(f'.//{{{NS}}}row[@r="4"]//{{{NS}}}t')]
            self.assertEqual('CMV histórico' in headers,cost)
            self.assertEqual('Margem de contribuição' in headers,margin)
            self.assertEqual(self.client.get(reverse('sales_sheet'),self.period).status_code,200)

    def test_export_permission_alone_cannot_read_and_operator_cannot_export(self):
        self.client.force_login(self.operator)
        for kind in ['sales','stock','purchases','payables','cash','titles','expenses','dre','dashboard']:
            self.assertEqual(self.client.get(self.url(kind),self.period).status_code,403)
        self.operator.user_permissions.add(Permission.objects.get(codename='export_dre'))
        self.assertEqual(self.client.get(self.url('dre'),self.period).status_code,403)

    def test_filters_all_rows_totals_only_confirmed_and_bad_request(self):
        self.confirmed();self.draft(invoice_number='101')
        self.client.force_login(self.actor)
        ds=build('sales',self.actor,{**self.period,'status':'all'})
        self.assertEqual(len(ds.rows),2);self.assertEqual(ds.totals['count'],1)
        self.assertEqual(ds.totals['revenue'],95)
        self.assertEqual(len(build('sales',self.actor,{**self.period,'q':'101','status':'all'}).rows),1)
        self.assertEqual(self.client.get(self.url('sales'),{'start':'invalid'}).status_code,400)
        self.assertEqual(self.client.post(self.url('sales'),self.period).status_code,405)
        self.assertEqual(self.client.get(self.url('unknown'),self.period).status_code,404)

    def test_typed_numbers_dates_and_formula_injection_protection(self):
        ds=Dataset('Teste',['Data','Valor','Texto'],[[self.today,D('12.345678'),'=HYPERLINK("bad")']])
        root=self.xml(xlsx(ds,'Empresa sintética'))
        self.assertEqual(root.find(f'.//{{{NS}}}c[@r="B5"]/{{{NS}}}v').text,'12.345678')
        self.assertEqual(root.find(f'.//{{{NS}}}c[@r="A5"]').get('s'),'3')
        self.assertEqual(root.find(f'.//{{{NS}}}c[@r="C5"]').get('t'),'inlineStr')
        self.assertEqual(root.findall(f'.//{{{NS}}}f'),[])

    def test_cash_horizontal_days_include_empty_days_and_detail(self):
        ds=build('cash',self.actor,dict(start=self.today,end=self.today+timedelta(days=1)))
        root=self.xml(xlsx(ds,'Empresa sintética'))
        self.assertEqual(len(root.findall(f'.//{{{NS}}}mergeCell')),2)
        self.assertEqual(root.find(f'.//{{{NS}}}c[@r="D3"]/{{{NS}}}v').text,'1000.00')
        self.assertIsNotNone(self.xml(xlsx(ds,'Empresa sintética'),2))

    def test_stock_multiple_locations_and_expense_historical_category(self):
        self.expense();self.category.name='Renomeada';self.category.save(update_fields=['name'])
        ds=build('expenses',self.actor,self.period)
        self.assertIn('Operacionais',ds.rows[0][3]);self.assertNotIn('Renomeada',ds.rows[0][3])
        ds=build('stock',self.actor,{})
        self.assertEqual(ds.locations.rows[0][2],str(self.location))

    def test_pdf_pagination_and_long_text(self):
        ds=Dataset('Teste',['Identificador','Descrição'],[[i,'Descrição longa '*80] for i in range(40)])
        content=pdf(ds,'Mercadovet sintética')
        self.assertTrue(content.startswith(b'%PDF-'));self.assertIn(b'%%EOF',content)

    def test_revoked_confirmation_is_blocked_in_service_and_http(self):
        sale=self.draft()
        AccessPolicy.objects.create(user=self.operator,rules={'core.confirm_sales':False})
        fresh=User.objects.get(pk=self.operator.pk)
        with self.assertRaises(PermissionDenied):services.confirm(actor=fresh,sale_id=sale.pk,revision=sale.revision)
        self.client.force_login(fresh)
        self.assertEqual(self.client.post(reverse('sale_confirm',args=[sale.pk]),{'revision':sale.revision}).status_code,403)

    def test_restricted_html_stays_paginated_without_export_limit(self):
        from unittest.mock import patch
        self.receive(self.product,D('100'),D('5'))
        for i in range(31):self.confirmed(invoice_number=str(i))
        self.operator.user_permissions.add(Permission.objects.get(codename='view_sales_report'))
        self.client.force_login(self.operator)
        with patch('apps.reporting.datasets.bound',side_effect=AssertionError('HTML must not build the full export')):
            r=self.client.get(reverse('sales_sheet'),{**self.period,'page':2})
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.context['page']),1)
        self.assertEqual(r.context['totals']['count'],31)
