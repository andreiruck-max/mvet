from datetime import date
from decimal import Decimal
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

class Company(models.Model):
    name = models.CharField("Nome", max_length=180, default="Mercadovet Produtos Agroveterinários")
    cutover_date = models.DateField("Data de corte", default=date(2026, 9, 15), editable=False)
    minimum_margin = models.DecimalField("Alerta de margem (%)", max_digits=6, decimal_places=2,
        default=Decimal("10.00"), validators=[MinValueValidator(0), MaxValueValidator(100)])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresa"
        permissions = [
            ("manage_configuration", "Gerenciar configurações da empresa"),
            ("view_dashboard", "Visualizar indicadores consolidados"),
            ("view_dre", "Visualizar DRE gerencial"),
            ("view_costs", "Visualizar custos e margens"),
            ("view_finance", "Visualizar contas e saldos financeiros"),
            ("operate_sales", "Lançar vendas operacionais"),
            ("operate_stock", "Lançar movimentações autorizadas de estoque"),
            ("operate_finance", "Lançar pagamentos e recebimentos"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="single_company"),
            models.CheckConstraint(condition=models.Q(minimum_margin__gte=0, minimum_margin__lte=100),
                                   name="valid_minimum_margin"),
        ]

    def __str__(self):
        return self.name

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="Usuário")
    occurred_at = models.DateTimeField("Data/hora", auto_now_add=True, db_index=True)
    entity = models.CharField("Entidade", max_length=120)
    entity_id = models.CharField("Identificador", max_length=80)
    operation = models.CharField("Operação", max_length=80)
    before = models.JSONField("Antes", default=dict)
    after = models.JSONField("Depois", default=dict)

    class Meta:
        verbose_name = "Registro de auditoria"
        verbose_name_plural = "Auditoria"
        ordering = ["-occurred_at", "-pk"]
