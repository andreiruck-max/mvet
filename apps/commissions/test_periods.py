from datetime import date
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from .forms import FilterForm

class CommissionPeriodsTests(SimpleTestCase):
    @patch('apps.commissions.forms.timezone.localdate',return_value=date(2026,10,14))
    def test_shortcuts_and_independent_receipt_dates(self, _):
        expected={'today':('2026-10-14','2026-10-14'),'yesterday':('2026-10-13','2026-10-13'),
            'last7':('2026-10-08','2026-10-14'),'week':('2026-10-12','2026-10-18'),
            'previous_week':('2026-10-05','2026-10-11'),'month':('2026-10-01','2026-10-31'),
            'previous_month':('2026-09-01','2026-09-30'),'year':('2026-01-01','2026-12-31')}
        for period,(start,end) in expected.items():
            form=FilterForm({'period':period,'received_start':'2026-09-10','q':'123'},actor=Mock())
            self.assertTrue(form.is_valid(),form.errors)
            self.assertEqual(form.cleaned_data['start'],date.fromisoformat(start))
            self.assertEqual(form.cleaned_data['end'],date.fromisoformat(end))
            self.assertEqual(form['start'].value(),start)
            self.assertEqual(form.cleaned_data['received_start'],date(2026,9,10))
            self.assertEqual(form.cleaned_data['q'],'123')

    def test_custom_and_unrestricted_dates(self):
        for data in [{},{'start':'2026-08-01','end':'2026-08-05'}]:
            form=FilterForm(data,actor=Mock())
            self.assertTrue(form.is_valid(),form.errors)
            self.assertEqual(form['start'].value(),data.get('start'))
        form=FilterForm({'start':'2026-08-05','end':'2026-08-01'},actor=Mock())
        self.assertFalse(form.is_valid())

    @patch('apps.commissions.forms.timezone.localdate',return_value=date(2028,3,1))
    def test_previous_month_leap_year(self, _):
        form=FilterForm({'period':'previous_month'},actor=Mock())
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['end'],date(2028,2,29))
