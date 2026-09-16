from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Company

ROLE_PERMISSIONS = {
    "ADMINISTRADOR": ["manage_configuration", "view_dashboard", "view_dre", "view_costs",
                      "view_finance", "operate_purchases", "view_purchase_reports", "operate_sales", "operate_stock", "operate_finance", "view_auditlog"],
    "GERENCIAL": ["view_dashboard", "view_dre", "view_costs", "view_purchase_reports"],
    "FINANCEIRO": ["view_finance", "operate_finance", "operate_purchases", "view_purchase_reports"],
    "VENDAS_OPERACIONAL": ["operate_sales"],
    "ESTOQUE": ["operate_stock"],
}

class Command(BaseCommand):
    help = "Cria empresa e perfis iniciais sem usuários, senhas ou dados comerciais."

    @transaction.atomic
    def handle(self, *args, **options):
        company, _ = Company.objects.get_or_create(pk=1)
        from apps.inventory.models import StockLocation
        # Initial editable catalog; existing warehouses/balances are never inferred.
        if not StockLocation.objects.exists():
            physical = StockLocation.objects.create(name="Estoque Mercadovet")
            StockLocation.objects.create(name="Estoque Full")
            company.default_stock_location = physical
            company.save(update_fields=["default_stock_location"])
        for name, codenames in ROLE_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=name)
            if created:
                group.permissions.set(Permission.objects.filter(
                    content_type__app_label="core", codename__in=codenames))
        self.stdout.write(self.style.SUCCESS("MVet configurado. Corte: 15/09/2026. Perfis existentes preservados."))
