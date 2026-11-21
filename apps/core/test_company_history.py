import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase
from apps.products.models import Product


class CompanyHistoryTests(TransactionTestCase):
    def test_baseline_detects_value_change_and_does_not_expose_values(self):
        product = Product.objects.create(sku='PRIVATE-SKU', name='Confidential product')
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'baseline.json'
            call_command('check_company_history', baseline=path, stdout=StringIO())
            text = path.read_text()
            self.assertNotIn('PRIVATE-SKU', text)
            self.assertNotIn('Confidential product', text)
            data = json.loads(text)
            self.assertEqual(data['models']['products.product']['count'], 1)
            call_command('check_company_history', compare=path, stdout=StringIO())
            with self.assertRaises(CommandError):
                call_command('check_company_history', baseline=path, stdout=StringIO())
            Product.objects.filter(pk=product.pk).update(name='Changed')
            with self.assertRaisesMessage(CommandError, 'products.product'):
                call_command('check_company_history', compare=path, stdout=StringIO())

    def test_baseline_detects_deletion_even_when_totals_would_match(self):
        product = Product.objects.create(sku='ZERO', name='Zero balance')
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'baseline.json'
            call_command('check_company_history', baseline=path, stdout=StringIO())
            product.delete()
            with self.assertRaisesMessage(CommandError, 'products.product'):
                call_command('check_company_history', compare=path, stdout=StringIO())


    def test_timestamp_microseconds_are_not_discarded(self):
        from django.contrib.auth.models import User
        from django.utils import timezone
        instant = timezone.now().replace(microsecond=100)
        user = User.objects.create(username='timestamp-test', date_joined=instant)
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'baseline.json'
            call_command('check_company_history', baseline=path, stdout=StringIO())
            User.objects.filter(pk=user.pk).update(date_joined=instant.replace(microsecond=101))
            with self.assertRaisesMessage(CommandError, 'auth.user'):
                call_command('check_company_history', compare=path, stdout=StringIO())
