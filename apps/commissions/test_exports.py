from io import BytesIO
from zipfile import ZipFile
from decimal import Decimal as D
from unittest.mock import patch
from django.test import TestCase
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
