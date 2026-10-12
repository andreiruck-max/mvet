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

    def test_complete_policy_does_not_inherit_new_capabilities(self):
        self.save(['core.operate_stock'])
        policy=AccessPolicy.objects.get(user=self.user)
        # Simulate a new capability absent from an already-reviewed policy.
        policy.rules.pop('core.adjust_stock');policy.save()
        self.assertTrue(self.fresh().has_perm('core.operate_stock'))
        self.assertFalse(self.fresh().has_perm('core.adjust_stock'))

    def test_native_employee_creation_does_not_accept_privilege_fields(self):
        self.client.force_login(self.master)
        password='Synthetic-Strong-Employee-729!'
        response=self.client.post(reverse('employee_new'),dict(username='employee',first_name='Pessoa',
            password1=password,password2=password,is_staff='on',is_superuser='on',permissions=['core.view_dre']))
        user=User.objects.get(username='employee')
        self.assertRedirects(response,reverse('user_access',args=[user.pk]))
        self.assertFalse(user.is_staff);self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_perm('core.view_dre'));self.assertTrue(user.check_password(password))
        self.assertTrue(AccessPolicy.objects.get(user=user).rules['__complete__'])
        self.assertNotIn(password,str(list(AuditLog.objects.values('before','after'))))

    def test_password_reset_authorization_validation_and_session_revocation(self):
        self.user.set_password('Old-Synthetic-Employee-729!');self.user.save()
        employee=Client();employee.login(username='local',password='Old-Synthetic-Employee-729!')
        self.client.force_login(self.user)
        for route in [reverse('employee_new'),reverse('employee_password',args=[self.user.pk])]:
            self.assertEqual(self.client.get(route).status_code,403)
            self.assertEqual(self.client.post(route,{}).status_code,403)
        self.client.force_login(self.master)
        self.assertEqual(self.client.get(reverse('employee_password',args=[self.master.pk])).status_code,403)
        url=reverse('employee_password',args=[self.user.pk])
        self.client.post(url,{'new_password1':'123','new_password2':'123'})
        self.assertTrue(self.fresh().check_password('Old-Synthetic-Employee-729!'))
        response=self.client.post(url,{'new_password1':'New-Synthetic-Employee-893!','new_password2':'New-Synthetic-Employee-893!'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(employee.get(reverse('home')).status_code,302)
        self.assertTrue(self.fresh().check_password('New-Synthetic-Employee-893!'))
        self.assertEqual(AuditLog.objects.filter(operation='reset_employee_password').count(),1)

    def test_settings_hub_does_not_grant_company_write_or_master_actions(self):
        from apps.core.models import Company
        Company.objects.create(pk=1)
        self.save(['core.manage_expense_rules']);self.client.force_login(self.user)
        response=self.client.get(reverse('configuration'))
        self.assertContains(response,'Plano de contas e despesas')
        self.assertNotContains(response,'Salvar configurações')
        self.assertNotContains(response,'Funcionários e permissões')
        self.assertEqual(self.client.post(reverse('configuration'),{'name':'Invadido'}).status_code,403)
        self.assertEqual(self.client.get(reverse('user_access_list')).status_code,403)
        self.assertNotEqual(Company.objects.get(pk=1).name,'Invadido')

    def test_profiles_are_explicit_and_grouped_catalog_is_complete(self):
        from .access import AccessForm, choices
        from .catalog import PROFILES, permission_groups
        codes={code.removeprefix('core.') for code,label in choices()}
        for profile in PROFILES.values():
            self.assertFalse(set(profile['codes'])-codes)
        options=[item['option'].data['value'] for group in permission_groups(AccessForm()) for item in group['items']]
        self.assertEqual(set(options),{'core.'+code for code in codes})
        self.assertEqual(len(options),len(codes))
