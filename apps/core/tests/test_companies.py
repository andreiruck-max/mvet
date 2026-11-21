from importlib import import_module
from unittest.mock import patch
from django.apps import apps
from django.contrib.auth.models import User, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase
from django.urls import reverse
from apps.accounts.company_access import has_company_permission, save_company_access
from apps.accounts.models import AccessPolicy, UserCompanyAccess
from apps.core.companies import save_company
from apps.core.models import Company, AuditLog


class CompanyFoundationTests(TestCase):
    def setUp(self):
        self.primary, _ = Company.objects.get_or_create(pk=1)
        self.agro, _ = Company.objects.get_or_create(pk=2, defaults={'name': 'MVet Agro', 'active': False})
        self.master = User.objects.create_superuser('company-master')
        self.employee = User.objects.create_user('company-employee')

    def grant(self, company_id=1, revision=0, **kwargs):
        data = dict(actor=self.master, user_id=self.employee.pk, company_id=company_id,
                    active=True, inherit_legacy=False, can_view_group=False,
                    permissions=['core.view_dashboard'], revision=revision)
        data.update(kwargs)
        return save_company_access(**data)

    def test_secondary_active_guard_is_enforced_in_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Company.objects.filter(pk=2).update(active=True)
        self.assertFalse(has_company_permission(self.master, 2, 'core.view_dashboard'))

    def test_company_creation_is_inactive_audited_and_cnpj_is_unique(self):
        company = save_company(actor=self.master, name='Laboratório sintético', cnpj='12345678000199')
        self.assertFalse(company.active)
        self.assertGreater(company.pk, 2)
        with self.assertRaises(ValidationError):
            save_company(actor=self.master, name='Duplicada', cnpj='12345678000199')
        self.assertEqual(AuditLog.objects.filter(operation='company_registry_saved').count(), 1)
        with self.assertRaises(ValidationError):
            save_company(actor=self.master, company_id=company.pk, name='Outra',
                         cnpj='98765432000100', revision=1)

    def test_revision_and_audit_rollback(self):
        save_company(actor=self.master, company_id=1, name='Mercadovet revisada', revision=0)
        with self.assertRaises(ValidationError):
            save_company(actor=self.master, company_id=1, name='Sobrescrita', revision=0)
        with patch('apps.core.companies.audit', side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):
                save_company(actor=self.master, company_id=1, name='Rollback', revision=1)
        self.primary.refresh_from_db()
        self.assertEqual(self.primary.name, 'Mercadovet revisada')
        self.assertEqual(self.primary.revision, 1)

    def test_missing_grant_and_revoked_grant_deny_access(self):
        self.employee.user_permissions.add(Permission.objects.get(codename='view_dashboard'))
        self.assertFalse(has_company_permission(self.employee, 1, 'core.view_dashboard'))
        self.grant()
        self.assertTrue(has_company_permission(self.employee, 1, 'core.view_dashboard'))
        self.assertFalse(has_company_permission(self.employee, 1, 'core.view_finance'))
        self.grant(revision=1, active=False)
        self.assertFalse(has_company_permission(self.employee, 1, 'core.view_dashboard'))
        self.assertEqual(AuditLog.objects.filter(operation='company_access_saved').count(), 2)

    def test_inactive_user_and_company_deny_even_with_grant(self):
        self.grant(company_id=2)
        self.assertFalse(has_company_permission(self.employee, 2, 'core.view_dashboard'))
        self.grant()
        self.employee.is_active = False
        self.employee.save()
        self.assertFalse(has_company_permission(self.employee, 1, 'core.view_dashboard'))

    def test_legacy_inheritance_preserves_explicit_denial(self):
        self.employee.user_permissions.add(Permission.objects.get(codename='view_dashboard'))
        AccessPolicy.objects.create(user=self.employee, rules={'core.view_dashboard': False})
        self.grant(inherit_legacy=True)
        self.assertFalse(has_company_permission(self.employee, 1, 'core.view_dashboard'))
        with self.assertRaises(ValidationError):
            self.grant(company_id=2, inherit_legacy=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserCompanyAccess.objects.create(user=self.employee, company=self.agro, inherit_legacy=True)

    def test_grant_rejects_invalid_codes_duplicate_revision_and_nonmaster(self):
        with self.assertRaises(ValidationError): self.grant(permissions=['auth.change_user'])
        with self.assertRaises(PermissionDenied): self.grant(actor=self.employee)
        self.grant()
        with self.assertRaises(ValidationError): self.grant()
        self.assertEqual(UserCompanyAccess.objects.filter(user=self.employee).count(), 1)

    def test_seed_preserves_primary_history_and_existing_rules(self):
        original = Company.objects.filter(pk=1).values().get()
        AccessPolicy.objects.create(user=self.employee, rules={'__complete__': True, 'core.view_dashboard': False})
        seed = import_module('apps.accounts.migrations.0003_seed_company_foundation').seed_foundation
        editor = connection.schema_editor(atomic=False)
        seed(apps, editor)
        seed(apps, editor)
        self.assertEqual(Company.objects.filter(pk=1).values().get(), original)
        grant = UserCompanyAccess.objects.get(user=self.employee, company_id=1)
        self.assertTrue(grant.inherit_legacy)
        self.assertFalse(grant.can_view_group)
        self.assertEqual(AccessPolicy.objects.get(user=self.employee).rules['core.view_dashboard'], False)
        self.assertEqual(UserCompanyAccess.objects.filter(user=self.employee).count(), 1)

    def test_registry_http_master_csrf_and_forged_activation(self):
        url = reverse('company_registry_edit', args=[2])
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.master)
        self.assertContains(self.client.get(url), 'empresas secundárias permanecem inativas')
        protected = Client(enforce_csrf_checks=True); protected.force_login(self.master)
        self.assertEqual(protected.post(url, {}).status_code, 403)
        self.client.post(url, {'name': 'MVet Agro', 'trade_name': 'Agro', 'cnpj': '', 'revision': 0, 'active': 'on'})
        self.agro.refresh_from_db(); self.assertFalse(self.agro.active)
        with self.assertRaises(PermissionDenied):
            save_company(actor=self.employee, name='Invasão')

    def test_company_access_http_and_user_cannot_self_grant(self):
        url = reverse('company_user_access', kwargs={'user_id': self.employee.pk, 'company_id': 2})
        self.client.force_login(self.employee)
        self.assertEqual(self.client.post(url, {'permissions': ['core.view_finance']}).status_code, 403)
        self.client.force_login(self.master)
        self.assertEqual(self.client.get(url).status_code, 200)
        protected = Client(enforce_csrf_checks=True); protected.force_login(self.master)
        self.assertEqual(protected.post(url, {}).status_code, 403)
        response = self.client.post(url, {'revision': 0, 'active': 'on', 'permissions': ['core.view_dashboard']})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(has_company_permission(self.employee, 2, 'core.view_dashboard'))
