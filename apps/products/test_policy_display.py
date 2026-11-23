from decimal import Decimal as D
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from apps.inventory.tests import StockFixtures
from apps.notifications.models import AlertConfiguration
from apps.notifications.services import conditions
from .models import CompanyProductPolicy


class PolicyDisplayTests(StockFixtures, TestCase):
    def test_forms_badge_detail_and_alert_read_same_policy(self):
        self.op()
        CompanyProductPolicy.objects.create(company_id=1,product=self.p,
            minimum=D('11'),markup=D('25'),fixed_sale_price=D('9'))
        self.client.force_login(self.actor)
        listing=self.client.get(reverse('products'),{'location':self.loc.pk})
        self.assertContains(listing,'Estoque mínimo')
        detail=self.client.get(reverse('product_detail',args=[self.p.pk]))
        self.assertEqual(detail.context['product'].commercial_minimum,D('11'))
        edit=self.client.get(reverse('product_edit',args=[self.p.pk]))
        self.assertEqual(edit.context['form'].initial['minimum'],D('11'))
        price=self.client.get(reverse('product_pricing',args=[self.p.pk]))
        self.assertEqual(price.context['form'].initial['markup'],D('25'))
        self.assertEqual(price.context['form'].initial['fixed_sale_price'],D('9'))
        config=AlertConfiguration(stock=True,margin=False,due=False,backup=False)
        alerts=list(conditions(config,timezone.now()))
        self.assertEqual([row[1] for row in alerts if row[0]=='STOCK'],[self.p.pk])
        self.assertIn('mínimo 11',alerts[0][3])
