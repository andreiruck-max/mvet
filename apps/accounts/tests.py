from django.contrib.auth.models import User, Permission, Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from apps.core.models import AuditLog
from .access import save_access
from .models import AccessPolicy


class AccessTests(TestCase):
    def setUp(self):
        self.master=User.objects.create_superuser('master')
        self.user=User.objects.create_user('local')

    def fresh(self):
        return User.objects.get(pk=self.user.pk)

    def save(self, permissions=(), **kwargs):
        return save_access(actor=self.master,user_id=self.user.pk,active=True,permissions=permissions,revision=0,**kwargs)

    def test_explicit_denial_overrides_direct_and_group_grants(self):
        p=Permission.objects.get(codename='view_costs');g=Group.objects.create(name='Custom');g.permissions.add(p)
        self.user.groups.add(g);self.user.user_permissions.add(p)
        self.assertTrue(self.fresh().has_perm('core.view_costs'))
        self.save(['core.view_dashboard'])
        self.assertFalse(self.fresh().has_perm('core.view_costs'))
        self.assertTrue(self.fresh().has_perm('core.view_dashboard'))
        self.assertFalse(self.fresh().has_perm('core.view_sales_report'))
        self.assertFalse(self.fresh().has_perm('core.view_margins'))
        self.assertFalse(self.fresh().has_perm('core.export_dashboard'))

    def test_specific_action_can_be_revoked_without_losing_module(self):
        self.user.user_permissions.add(Permission.objects.get(codename='operate_sales'))
        self.assertTrue(self.fresh().has_perm('core.confirm_sales'))
        self.save(['core.operate_sales','core.view_sales'])
        self.assertTrue(self.fresh().has_perm('core.operate_sales'))
        self.assertFalse(self.fresh().has_perm('core.confirm_sales'))

    def test_only_master_and_no_master_mutation_or_unknown_permission(self):
        self.user.is_staff=True;self.user.save()
        self.user.user_permissions.add(Permission.objects.get(codename='manage_configuration'))
        with self.assertRaises(PermissionDenied):save_access(actor=self.user,user_id=self.user.pk,active=True,permissions=[],revision=0)
        with self.assertRaises(ValidationError):save_access(actor=self.master,user_id=self.master.pk,active=True,permissions=[],revision=0)
        with self.assertRaises(ValidationError):self.save(['auth.change_user'])
        self.assertFalse(AccessPolicy.objects.exists())

    def test_audit_revision_and_inactivation(self):
        self.save(['core.view_dashboard'])
        with self.assertRaises(ValidationError):self.save([])
        save_access(actor=self.master,user_id=self.user.pk,active=False,permissions=['core.view_dashboard'],revision=1)
        self.assertFalse(self.fresh().has_perm('core.view_dashboard'))
        self.assertEqual(AuditLog.objects.filter(operation='set_access_policy').count(),2)

    def test_http_master_csrf_and_revocation_on_next_request(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('user_access_list')).status_code,403)
        self.client.force_login(self.master)
        self.assertEqual(self.client.get(reverse('user_access_list')).status_code,200)
        self.assertEqual(self.client.get(reverse('user_access',args=[self.user.pk])).status_code,200)
        protected=Client(enforce_csrf_checks=True);protected.force_login(self.master)
        self.assertEqual(protected.post(reverse('user_access',args=[self.user.pk]),{}).status_code,403)
        from apps.core.models import Company
        Company.objects.create(pk=1)
        self.save(['core.view_dashboard']);self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)
        save_access(actor=self.master,user_id=self.user.pk,active=True,permissions=[],revision=1)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code,403)
