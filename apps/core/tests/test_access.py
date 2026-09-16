from datetime import date
from decimal import Decimal
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from apps.core.models import AuditLog, Company
from apps.core.services import update_company

class FoundationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_mvet", verbosity=0)
        cls.operator = User.objects.create_user("operator", password="Strong-Test-Password-95!")
        cls.operator.groups.add(Group.objects.get(name="VENDAS_OPERACIONAL"))
        cls.manager = User.objects.create_user("manager", password="Strong-Test-Password-95!")
        cls.manager.groups.add(Group.objects.get(name="GERENCIAL"))
        cls.configurator = User.objects.create_user("configurator", password="Strong-Test-Password-95!")
        cls.configurator.user_permissions.add(Permission.objects.get(codename="manage_configuration"))
        cls.admin = User.objects.create_superuser("root", email="root@example.test", password="Strong-Test-Password-95!")

    def test_anonymous_requires_authentication(self):
        for name in ["home", "configuration", "dashboard", "dre", "finance", "dashboard_api"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_operator_cannot_access_consolidated_routes_or_api(self):
        self.client.force_login(self.operator)
        for name in ["dashboard", "dre", "finance", "configuration", "dashboard_api"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertContains(self.client.get(reverse("home")), "MVet 1.0")
        self.assertNotContains(self.client.get(reverse("home")), 'href="/indicadores/"')
        self.assertNotContains(self.client.get(reverse("home")), 'href="/financeiro/"')

    def test_manager_does_not_gain_configuration_or_bank_access(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dre")).status_code, 200)
        self.assertEqual(self.client.get(reverse("finance")).status_code, 403)
        self.assertEqual(self.client.get(reverse("configuration")).status_code, 403)
        response = self.client.get(reverse("dashboard_api"))
        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["status"], "not_implemented")

    def test_forged_post_does_not_bypass_permission(self):
        self.client.force_login(self.operator)
        response = self.client.post(reverse("configuration"), {"name": "Changed", "minimum_margin": "1"})
        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(Company.objects.get(pk=1).name, "Changed")

    def test_service_enforces_permission_without_http(self):
        with self.assertRaises(PermissionDenied):
            update_company(actor=self.operator, name="Changed", minimum_margin=Decimal("5"))
        self.assertNotEqual(Company.objects.get(pk=1).name, "Changed")

    def test_configuration_is_audited_and_cutover_is_not_editable(self):
        self.client.force_login(self.configurator)
        response = self.client.post(reverse("configuration"), {
            "name": "Mercadovet", "minimum_margin": "12,50", "cutover_date": "2020-01-01"})
        self.assertRedirects(response, reverse("configuration"))
        company = Company.objects.get(pk=1)
        self.assertEqual(company.minimum_margin, Decimal("12.50"))
        self.assertEqual(company.cutover_date, date(2026, 9, 15))
        log = AuditLog.objects.get(operation="update_configuration")
        self.assertEqual(log.actor_id, self.configurator.pk)
        self.assertEqual(log.before["minimum_margin"], "10.00")
        self.assertEqual(log.after["minimum_margin"], "12.50")

    def test_invalid_margin_rolls_back_configuration(self):
        before = Company.objects.get(pk=1).name
        for value in [Decimal("-1"), Decimal("101")]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                update_company(actor=self.configurator, name="Changed", minimum_margin=value)
        self.assertEqual(Company.objects.get(pk=1).name, before)
        self.assertFalse(AuditLog.objects.filter(operation="update_configuration").exists())

    def test_float_is_rejected_in_service(self):
        with self.assertRaises(ValidationError):
            update_company(actor=self.configurator, name="Changed", minimum_margin=10.1)

    def test_company_singleton_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Company.objects.create(pk=2)

    def test_setup_is_idempotent_and_preserves_custom_roles(self):
        group = Group.objects.get(name="VENDAS_OPERACIONAL")
        group.permissions.clear()
        call_command("setup_mvet", verbosity=0)
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(Group.objects.filter(name="VENDAS_OPERACIONAL").count(), 1)
        self.assertEqual(group.permissions.count(), 0)

    def test_csrf_required_for_configuration(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.configurator)
        self.assertEqual(client.post(reverse("configuration"), {"name": "Changed", "minimum_margin": "5"}).status_code, 403)

    def test_logout_requires_post(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
        self.assertTrue(AuditLog.objects.filter(actor=self.operator, operation="logout").exists())

    def test_inactive_user_cannot_login(self):
        self.operator.is_active = False
        self.operator.save(update_fields=["is_active"])
        self.assertFalse(self.client.login(username="operator", password="Strong-Test-Password-95!"))

    def test_finance_permission_is_independent(self):
        user = User.objects.create_user("finance")
        user.groups.add(Group.objects.get(name="FINANCEIRO"))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("finance")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dre")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard_api")).status_code, 403)

    def test_staff_cannot_promote_themselves_through_admin(self):
        self.operator.is_staff = True
        self.operator.save(update_fields=["is_staff"])
        self.operator.user_permissions.add(Permission.objects.get(codename="change_user", content_type__app_label="auth"))
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("admin:auth_user_change", args=[self.operator.pk])).status_code, 403)

    def test_audit_admin_is_read_only_even_for_superuser(self):
        self.client.force_login(self.admin)
        log = AuditLog.objects.first()
        self.assertEqual(self.client.get(reverse("admin:core_auditlog_changelist")).status_code, 200)
        self.assertEqual(self.client.post(reverse("admin:core_auditlog_change", args=[log.pk]), {"operation": "tampered"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:core_auditlog_delete", args=[log.pk]), {"post": "yes"}).status_code, 403)

    def test_valid_login_is_audited_without_passwords(self):
        self.assertTrue(self.client.login(username="operator", password="Strong-Test-Password-95!"))
        log = AuditLog.objects.get(operation="login", actor=self.operator)
        self.assertEqual(log.before, {})
        self.assertEqual(log.after, {})

    def test_password_change_is_audited_and_session_remains_valid(self):
        self.client.force_login(self.operator)
        response = self.client.post(reverse("password_change"), {
            "old_password": "Strong-Test-Password-95!",
            "new_password1": "Another-Test-Password-92!",
            "new_password2": "Another-Test-Password-92!",
        })
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(AuditLog.objects.filter(operation="change_password", actor=self.operator).exists())
        self.operator.refresh_from_db()
        self.assertTrue(self.operator.check_password("Another-Test-Password-92!"))

    def test_login_template_and_security_headers(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_empty_setup_has_useful_message(self):
        Company.objects.all().delete()
        self.client.force_login(self.configurator)
        response = self.client.get(reverse("configuration"))
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "Configuração inicial pendente", status_code=503)
