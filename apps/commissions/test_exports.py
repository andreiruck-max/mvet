from io import BytesIO
from zipfile import ZipFile
from decimal import Decimal as D
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from .tests import Fixture
from .models import Payee
from . import services as s

class ExportTests(Fixture, TestCase):
    def test_monthly_formats_snapshot_and_payment_totals(self):
        plan = self.plan()
        self.receipt(plan)
        self.payment('10')
        self.client.force_login(self.actor)
        url = reverse('commission_monthly')
        params = {'month':self.today.strftime('%Y-%m'), 'payee':self.payee.pk, 'export':'xlsx'}
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as book:
            summary = book.read('xl/worksheets/sheet1.xml').decode()
            detail = book.read('xl/worksheets/sheet2.xml').decode()
            paid = book.read('xl/worksheets/sheet3.xml').decode()
        self.assertIn('22.50', summary)
        self.assertIn('12.50', summary)
        self.assertIn('900.00', detail)
        self.assertIn('5.0000', detail)
        self.assertIn('PIX', paid)
        self.assertNotIn('CMV', detail)
        self.assertNotIn('Margem', detail)
        params['export'] = 'pdf'
        response = self.client.get(url, params)
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_own_scope_and_invalid_filters(self):
        plan = self.plan()
        self.receipt(plan)
        other = Payee.objects.create(name='OUTRO-VENDEDOR-RESTRITO')
        self.client.force_login(self.employee)
        url = reverse('commission_monthly')
        params = {'month':self.today.strftime('%Y-%m'), 'payee':other.pk, 'export':'xlsx'}
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as book:
            xml = ''.join(book.read(f'xl/worksheets/sheet{i}.xml').decode() for i in (1,2,3))
        self.assertIn(self.payee.name, xml)
        self.assertNotIn(other.name, xml)
        self.assertEqual(self.client.get(url, {'month':'invalid','export':'pdf'}).status_code, 400)
        self.assertEqual(self.client.get(url, {'export':'csv'}).status_code, 400)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url, params).status_code, 403)

    def test_reversal_and_historical_rate_are_exported(self):
        from uuid import uuid4
        plan = self.plan()
        event = self.receipt(plan)
        self.payment('10')
        plan.refresh_from_db()
        s.adjust(actor=self.actor,plan_id=plan.pk,revision=plan.revision,rate=D('8'),
                 override_total=None,key=uuid4(),reason='Novo percentual')
        s.reverse_receipt(actor=self.actor,entry_id=event.pk,date=self.today,key=uuid4(),reason='Estorno teste')
        self.client.force_login(self.actor)
        with patch('apps.commissions.exports.xlsx', return_value=b'book') as render:
            response = self.client.get(reverse('commission_monthly'), {'export':'xlsx','month':self.today.strftime('%Y-%m')})
        self.assertEqual(response.status_code, 200)
        dataset = render.call_args.args[0]
        self.assertEqual(dataset.rows[0][-1], D('-10'))
        detail = dataset.sections[0]
        self.assertEqual(detail.rows[0][7], D('5'))
        self.assertTrue(any(row[12] < 0 for row in detail.rows))


class CompactPDFTests(SimpleTestCase):
    def statement(self, count=10, payee_id=1):
        from datetime import date
        from types import SimpleNamespace as N
        class Person:
            pk = payee_id
            def __str__(self): return f'Comissionado sintético {self.pk}'
        person = Person()
        row = dict(payee=person, released=D(count), paid=D(0), month_allocated=D(0),
                   pending=D(count), previous=D(0), total=D(count))
        events = []
        for i in range(count):
            plan = N(payee_id=person.pk, customer='Cliente sintético com nome completo',
                     sale=N(reference=f'NF-SINTETICA-{i:03}', date=date(2026,10,1)))
            events.append(N(installment=N(plan=plan,number=1),date=date(2026,10,2),
                            command=N(reason='Recebimento Pix'),received=D('50'),released=D('1'),paid=D(0),pending=D('1'),
                            terms=dict(base='50',rate='2',total='1',installment_forecast='1')))
        return row, events

    def test_ten_commissions_fit_one_page_with_all_rows_and_notes(self):
        from datetime import date
        from apps.reporting.test_pdf_layout import pages, render_with_text
        from .exports import render_pdf, NOTES
        row, events = self.statement()
        content, drawn = render_with_text(render_pdf, [row], events, [], date(2026,10,1),date(2026,10,31),'Empresa sintética')
        self.assertEqual(pages(content), 1)
        for i in range(10):
            self.assertTrue(any(f'NF-SINTETICA-{i:03}' in text for _,text in drawn))
        self.assertIn((1, NOTES), drawn)

    def test_long_statement_starts_on_summary_page_and_keeps_last_record(self):
        from datetime import date
        from apps.reporting.test_pdf_layout import pages, render_with_text
        from .exports import render_pdf
        row, events = self.statement(80)
        events[-1].released = D('-12.34')
        events[-1].terms['total'] = '15.67'
        events[-1].command.reason = 'Ajuste manual auditado'
        content, drawn = render_with_text(render_pdf, [row], events, [], date(2026,10,1),date(2026,10,31),'Empresa sintética')
        self.assertGreater(pages(content), 1)
        self.assertTrue(any(page == 1 and 'NF-SINTETICA-000' in text for page,text in drawn))
        self.assertTrue(any('NF-SINTETICA-079' in text for _,text in drawn))
        self.assertTrue(any(text == '-12,34' for _,text in drawn))
        self.assertTrue(any('15,67 / 1,00' in text for _,text in drawn))

    def test_separate_payees_and_payment_reversal(self):
        from datetime import date
        from types import SimpleNamespace as N
        from apps.reporting.test_pdf_layout import pages, render_with_text
        from .exports import render_pdf
        first, a = self.statement(1)
        second, b = self.statement(1,2)
        payment = N(payee_id=2,date=date(2026,10,5),method='PIX',reversal_of_id=1,
                    amount=D('-1'),command=N(reason='ESTORNO-SINTETICO'))
        content, drawn = render_with_text(render_pdf, [first,second], a+b, [payment], date(2026,10,1),date(2026,10,31),'Empresa sintética')
        self.assertEqual(pages(content), 2)
        self.assertIn((2, 'ESTORNO-SINTETICO'), drawn)
        self.assertNotIn((1, 'ESTORNO-SINTETICO'), drawn)
