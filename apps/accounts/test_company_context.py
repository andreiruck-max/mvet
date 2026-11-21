from django.contrib.auth.models import User, AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from apps.core.models import Company
from .models import UserCompanyAccess
from .company_context import resolve_scope


class CompanyContextTests(TestCase):
    def setUp(self):
        Company.objects.get_or_create(pk=1)
        Company.objects.get_or_create(pk=2, defaults={'active':False})
        self.user = User.objects.create_user('scope-test')
        self.master = User.objects.create_superuser('scope-master')

    def test_denies_missing_inactive_or_invalid_context_without_fallback(self):
        for user, selection in [(self.user,1),(self.master,2),(self.master,'bad'),(AnonymousUser(),1)]:
            with self.assertRaises(PermissionDenied):
                resolve_scope(user, selection)

    def test_revocation_is_rechecked_and_group_cannot_write(self):
        grant = UserCompanyAccess.objects.create(user=self.user,company_id=1,active=True,can_view_group=True)
        self.assertEqual(resolve_scope(self.user,'1').require_operation(),1)
        scope = resolve_scope(self.user,'group')
        self.assertEqual(scope.company_ids,(1,))
        with self.assertRaises(PermissionDenied): scope.require_operation()
        grant.active=False;grant.save()
        with self.assertRaises(PermissionDenied): resolve_scope(self.user,1)

    def test_group_requires_explicit_grant(self):
        UserCompanyAccess.objects.create(user=self.user,company_id=1,active=True)
        with self.assertRaises(PermissionDenied): resolve_scope(self.user,'group')
        self.user.is_active=False;self.user.save()
        with self.assertRaises(PermissionDenied): resolve_scope(self.user,1)


from django.test import override_settings, Client
from django.urls import reverse


@override_settings(COMPANY_CONTEXT_ENABLED=True)
class CompanySessionTests(CompanyContextTests):
    def test_session_switch_blocks_legacy_group_routes_and_can_return(self):
        self.client.force_login(self.master)
        url=reverse('company_context')
        self.assertContains(self.client.get(url),'Selecionar contexto')
        self.assertEqual(self.client.post(url,{'company':'group'}).status_code,302)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,403)
        self.assertEqual(self.client.get(reverse('dashboard_api')).status_code,403)
        self.assertEqual(self.client.post(url,{'company':'1'}).status_code,302)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)

    def test_revoked_grant_invalid_selection_and_csrf(self):
        grant=UserCompanyAccess.objects.create(user=self.user,company_id=1,active=True,rules={'core.view_dashboard':True})
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)
        self.assertEqual(self.client.get(reverse('dre')).status_code,403)
        url=reverse('company_context')
        self.assertEqual(self.client.post(url,{'company':'2'}).status_code,403)
        self.assertNotIn('company_selection',self.client.session)
        grant.active=False;grant.save()
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,403)
        secure=Client(enforce_csrf_checks=True);secure.force_login(self.master)
        self.assertEqual(secure.post(url,{'company':'group'}).status_code,403)
