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
