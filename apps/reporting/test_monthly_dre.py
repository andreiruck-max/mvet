from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from .drilldown import monthly_lines
from .tests import ReportingFixture


class CalendarColumnsTests(SimpleTestCase):
    def test_clips_partial_months_across_year_and_preserves_channel(self):
        data = dict(start=date(2025,12,20), end=date(2026,2,3), channel=object())
        def report(period):
            return {'provisional': False, 'days': (period['end']-period['start']).days+1}
        def lines(r, d, master):
            return [{'label':'Total','value':Decimal(r['days']), 'url':None}]
        with patch('apps.reporting.drilldown.selectors.dre', side_effect=report) as query, patch('apps.reporting.drilldown.lines', side_effect=lines):
            total, columns, rows = monthly_lines(data)
        self.assertEqual([c['label'] for c in columns], ['12/2025','01/2026','02/2026'])
        self.assertEqual([c['value'] for c in rows[0]['months']], [12,31,3])
        self.assertEqual(rows[0]['value'], 46)
        self.assertTrue(all(call.args[0]['channel'] is data['channel'] for call in query.call_args_list))


class MonthlyDRETests(ReportingFixture, TestCase):
    def test_months_reconcile_with_total_and_link_dates(self):
        self.expense(amount=Decimal('13.27'))
        self.client.force_login(self.actor)
        period = dict(start=self.company.cutover_date, end=self.today)
        response = self.client.get(reverse('dre'), period)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.context['months']), 2)
        for row in response.context['lines']:
            self.assertEqual(sum(c['value'] for c in row['months']), row['value'])
        self.assertContains(response, 'Total (R$)')
        self.assertContains(response, 'Exportações Excel/PDF')
        self.assertTrue(any(c['url'] for row in response.context['lines'] for c in row['months']))
