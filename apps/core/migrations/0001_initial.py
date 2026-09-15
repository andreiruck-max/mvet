import datetime
import decimal
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="Mercadovet Produtos Agroveterinários", max_length=180, verbose_name="Nome")),
                ("cutover_date", models.DateField(default=datetime.date(2026, 9, 15), editable=False, verbose_name="Data de corte")),
                ("minimum_margin", models.DecimalField(decimal_places=2, default=decimal.Decimal("10.00"),
                    max_digits=6, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)],
                    verbose_name="Alerta de margem (%)")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Empresa", "verbose_name_plural": "Empresa",
                "permissions": [
                    ("manage_configuration", "Gerenciar configurações da empresa"),
                    ("view_dashboard", "Visualizar indicadores consolidados"),
                    ("view_dre", "Visualizar DRE gerencial"),
                    ("view_costs", "Visualizar custos e margens"),
                    ("view_finance", "Visualizar contas e saldos financeiros"),
                    ("operate_sales", "Lançar vendas operacionais"),
                    ("operate_stock", "Lançar movimentações autorizadas de estoque"),
                    ("operate_finance", "Lançar pagamentos e recebimentos"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(("id", 1)), name="single_company"),
                    models.CheckConstraint(condition=models.Q(("minimum_margin__gte", 0), ("minimum_margin__lte", 100)), name="valid_minimum_margin"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Data/hora")),
                ("entity", models.CharField(max_length=120, verbose_name="Entidade")),
                ("entity_id", models.CharField(max_length=80, verbose_name="Identificador")),
                ("operation", models.CharField(max_length=80, verbose_name="Operação")),
                ("before", models.JSONField(default=dict, verbose_name="Antes")),
                ("after", models.JSONField(default=dict, verbose_name="Depois")),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL, verbose_name="Usuário")),
            ],
            options={"verbose_name": "Registro de auditoria", "verbose_name_plural": "Auditoria",
                     "ordering": ["-occurred_at", "-pk"]},
        ),
    ]
