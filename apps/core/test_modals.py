from types import SimpleNamespace
from django.test import SimpleTestCase, RequestFactory, TestCase
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse, resolve
from .modals import QUICK_ACTIONS, action_patterns, ActionModalMiddleware
from apps.finance.tests import Fixture
import re


class ModalPolicyTests(SimpleTestCase):
    def test_routes_are_explicit_and_long_flows_are_not_modals(self):
        patterns=action_patterns()
        for name,args in [('financial_transfer',[]),('commission_schedule',[3]),('crm_state',[3,'pause']),('product_count',[2,1]),('expense_edit',[3])]:
            self.assertTrue(any(re.fullmatch(p,reverse(name,args=args)) for p in patterns),name)
        for name in ['sale_new','purchase_new','inventory_reconcile','bling_queue','finance','crm_import','expense_bulk_payment']:
            self.assertFalse(any(re.fullmatch(p,reverse(name)) for p in patterns),name)
        self.assertGreater(len(patterns),25)

    def request(self, method='get', name='financial_transfer', modal=True):
        path=reverse(name)+('?_modal=1' if modal else '')
        req=getattr(RequestFactory(),method)(path)
        req.resolver_match=resolve(req.path)
        req.user=SimpleNamespace(is_authenticated=True,has_perm=lambda name:False,is_superuser=False,is_staff=False,pk=1)
        req.session={}
        return req

    def test_success_returns_completion_without_consuming_messages(self):
        req=self.request('post')
        response=ActionModalMiddleware(lambda r:HttpResponseRedirect(reverse('financial_accounts')))(req)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'data-modal-complete="true"')
        self.assertEqual(response['X-Frame-Options'],'SAMEORIGIN')
        self.assertEqual(response['Cache-Control'],'no-store')

    def test_validation_and_non_modal_responses_are_not_swallowed(self):
        bad=HttpResponse('Validation error',status=400)
        self.assertIs(ActionModalMiddleware(lambda r:bad)(self.request('post')),bad)
        for req in [self.request('post',modal=False),self.request('post',name='sale_new')]:
            response=ActionModalMiddleware(lambda r:HttpResponseRedirect('/'))(req)
            self.assertEqual(response.status_code,302)
            self.assertNotIn('X-Frame-Options',response)

    def test_get_redirect_carries_mode_but_external_redirect_is_not_completion(self):
        response=ActionModalMiddleware(lambda r:HttpResponseRedirect('/despesas/1/editar/?next=abc'))(self.request())
        self.assertIn('_modal=1',response['Location'])
        self.assertIn('next=abc',response['Location'])
        response=ActionModalMiddleware(lambda r:HttpResponseRedirect('https://example.org'))(self.request('post'))
        self.assertEqual(response.status_code,302)


class ModalAccessTests(Fixture,TestCase):
    def test_auth_permission_and_csrf_are_preserved(self):
        from django.test import Client
        from uuid import uuid4
        target=reverse('financial_transfer')+'?_modal=1'
        self.assertEqual(self.client.get(target).status_code,302)
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(target).status_code,403)
        self.client.force_login(self.operator)
        response=self.client.get(target)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['X-Frame-Options'],'SAMEORIGIN')
        self.assertContains(response,'data-modal-mode="true"')
        self.assertNotContains(response,'<aside class="sidebar">')
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.operator)
        self.assertEqual(csrf.post(target,{'key':uuid4()}).status_code,403)
        normal=self.client.get(reverse('financial_transfer'))
        self.assertEqual(normal['X-Frame-Options'],'DENY')
        self.assertContains(normal,'<aside class="sidebar">')
