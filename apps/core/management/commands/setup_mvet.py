from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Company

ROLE_PERMISSIONS = {
    "ADMINISTRADOR": ["manage_configuration", "view_dashboard", "view_dre", "view_costs",
                      "view_finance", "operate_sales", "operate_stock", "operate_finance", "view_auditlog"],
    "GERENCIAL": ["view_dashboard", "view_dre", "view_costs"],
    "FINANCEIRO": ["view_finance", "operate_finance"],
    "VENDAS_OPERACIONAL": ["operate_sales"],
    "ESTOQUE": ["operate_stock"],
}

class Command(BaseCommand):
    help = "Cria empresa e perfis iniciais sem usuários, senhas ou dados comerciais."

    @transaction.atomic
    def handle(self, *args, **options):
        Company.objects.get_or_create(pk=1)
        for name, codenames in ROLE_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=name)
            if created:
                group.permissions.set(Permission.objects.filter(
                    content_type__app_label="core", codename__in=codenames))
        self.stdout.write(self.style.SUCCESS("MVet configurado. Corte: 15/09/2026. Perfis existentes preservados."))
