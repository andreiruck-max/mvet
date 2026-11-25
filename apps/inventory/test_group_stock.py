from decimal import Decimal as D
from uuid import uuid4

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import AccessPolicy, UserCompanyAccess
from apps.core.models import Company
from apps.products.models import Product
from .models import StockOperation
from .services import _apply, domain_lock
from .tests import DAY, StockFixtures


@override_settings(COMPANY_CONTEXT_ENABLED=True)
class GroupStockTests(StockFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.agro, _ = Company.objects.get_or_create(pk=2,defaults={'active':False})
        self.agro.trade_name = 'Segunda proprietária'
        self.agro.save(update_fields=['trade_name'])
        self.url = reverse('group_stock')

    def open_group(self, user):
        self.client.force_login(user)
        self.assertEqual(self.client.post(reverse('company_context'),{'company':'group'}).status_code,302)

    def leg(self, owner, quantity, value, kind='RECEIPT', *, reference=None):
        domain_lock()
        op=StockOperation.objects.create(company_id=owner, key=uuid4(), actor=self.actor, date=DAY,
            kind=kind, reason='Teste da posição física', fingerprint='fixture-position')
        product=Product.objects.select_for_update().get(pk=self.p.pk)
        return _apply(op,product,self.loc,D(quantity),D(value),unit_cost=D(reference) if reference else None)

    def row(self, **extra):
        response=self.client.get(self.url, dict({'location':self.loc.pk,'q':self.p.sku},**extra))
        self.assertEqual(response.status_code,200)
        return response, response.context['page'][0]

    def test_physical_and_negative_positions_in_both_directions(self):
        self.open_group(self.actor)
        self.leg(1,'10','50')
        self.leg(2,'0','0','REVALUE',reference='7')
        self.leg(2,'-2','-14','SALE_OUT')
        response,row=self.row()
        self.assertContains(response,'Físico do depósito')
        self.assertEqual((row['total'],[(c['quantity'],c['cost']) for c in row['cells']]),(8,[(10,5),(-2,7)]))
        self.leg(1,'-2','-10','TRANSFER'); self.leg(2,'2','14','TRANSFER')
        self.assertEqual(self.row()[1]['total'],8)
        self.leg(2,'5','65')  # Own purchase; does not affect the other owner's cost.
        self.leg(1,'-10','-50','SALE_OUT')
        row=self.row()[1]
        self.assertEqual((row['total'],[(c['quantity'],c['cost']) for c in row['cells']]),(3,[(-2,5),(5,13)]))
        self.leg(2,'-2','-26','TRANSFER'); self.leg(1,'2','26','TRANSFER')
        self.assertEqual(self.row()[1]['total'],3)
        self.op(location_id=self.full.pk,quantity=D('20'),cost=D('9'))
        self.assertEqual(self.row(location=self.full.pk)[1]['total'],20)
        self.assertEqual(self.row()[1]['total'],3)

    def test_zero_physical_can_have_offsetting_positions_and_all_lists_zero_products(self):
        self.open_group(self.actor)
        self.leg(1,'2','10'); self.leg(2,'0','0','REVALUE',reference='7')
        self.leg(2,'-2','-14','SALE_OUT')
        self.assertEqual(self.row()[1]['total'],0)
        Product.objects.bulk_create([Product(sku=str(n),name='Produto de catálogo') for n in range(2,55)])
        Product.objects.create(sku='1',name='Kit virtual',kind='KIT')
        q={'location':self.loc.pk,'position':'all'}
        first=self.client.get(self.url,q).context['page']
        self.assertEqual((len(first),first[0]['sku'],first[-1]['sku']),(50,'2','51'))
        self.assertEqual(first[0]['total'],0)
        second=self.client.get(self.url,dict(q,page=2)).context['page']
        self.assertEqual([row['sku'] for row in second],['52','53','54',self.p.sku])
        self.assertFalse(self.client.get(self.url,{'location':'999999'}).context['form'].is_valid())

    def test_grant_cost_separation_and_no_foreign_subtotal(self):
        self.leg(1,'7','140'); self.leg(2,'3','296.296296')
        user=User.objects.create_user('group-stock-reader')
        grant=UserCompanyAccess.objects.create(user=user,company_id=1,can_view_group=True,
            rules={'core.view_stock':True})
        self.open_group(user)
        response,row=self.row(company=2, costs='1')
        self.assertContains(response,'Subtotal autorizado')
        self.assertNotContains(response,self.agro.trade_name)
        self.assertNotContains(response,'Custo médio (R$)')
        self.assertEqual((row['total'],row['cells']), (7,[{'quantity':7,'cost':None,'show_cost':False}]))
        grant.rules={'core.view_stock':True,'core.view_costs':True};grant.save()
        self.assertEqual(self.row()[1]['cells'][0]['cost'],20)
        grant.rules={'core.view_costs':True};grant.save()
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.assertNotContains(self.client.get(reverse('company_context')),'Consultar estoque do grupo')
        grant.active=False;grant.save()
        self.assertEqual(self.client.get(self.url).status_code,403)

    def test_inherited_access_keeps_explicit_denial(self):
        self.leg(1,'2','10')
        user=User.objects.create_user('inherited-stock-reader')
        user.user_permissions.add(Permission.objects.get(codename='operate_stock'),
                                  Permission.objects.get(codename='view_costs'))
        UserCompanyAccess.objects.create(user=user,company_id=1,can_view_group=True,inherit_legacy=True)
        AccessPolicy.objects.create(user=user,rules={'core.view_costs':False})
        self.open_group(user)
        self.assertEqual(self.row()[1]['cells'],[{'quantity':2,'cost':None,'show_cost':False}])

    def test_only_group_and_read_only(self):
        self.client.force_login(self.actor)
        self.assertEqual(self.client.get(self.url,{'company':'group'}).status_code,403)
        self.open_group(self.actor)
        before=StockOperation.objects.count()
        self.assertEqual(self.client.post(self.url,{'quantity':'50'}).status_code,405)
        self.assertEqual(self.client.post(reverse('operation_new'),{}).status_code,403)
        self.assertEqual(StockOperation.objects.count(),before)
        with self.settings(COMPANY_CONTEXT_ENABLED=False):
            self.assertEqual(self.client.get(self.url).status_code,404)
