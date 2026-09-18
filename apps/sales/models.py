import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from apps.products.models import NamedActive, Product
from apps.inventory.models import StockLocation, StockOperation, StockMovement, Immutable


def money(label):
    return models.DecimalField(label, max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(0)])

class SalesChannel(NamedActive):
    class Meta:
        ordering = ['name']

class TaxRule(models.Model):
    name = models.CharField('Nome', max_length=120)
    rate = models.DecimalField('Alíquota (%)', max_digits=7, decimal_places=4, validators=[MinValueValidator(0), MaxValueValidator(100)])
    starts_on = models.DateField('Início da vigência')
    ends_on = models.DateField('Fim da vigência', null=True, blank=True)
    base = models.CharField('Base de cálculo', max_length=20, choices=[('REVENUE','Receita operacional, incluindo ajuste gerencial'),('PRODUCTS','Produtos − desconto')])
    active = models.BooleanField('Ativa', default=True)
    class Meta:
        ordering = ['name', '-starts_on']
        constraints = [models.CheckConstraint(condition=models.Q(rate__gte=0,rate__lte=100),name='sales_tax_rate_range'), models.CheckConstraint(condition=models.Q(ends_on__isnull=True)|models.Q(ends_on__gte=models.F('starts_on')),name='sales_tax_dates')]
    def __str__(self): return self.name

class Sale(models.Model):
    key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    creation_fingerprint = models.CharField(max_length=64, editable=False)
    revision = models.PositiveIntegerField(default=0, editable=False)
    date = models.DateField('Data da venda', db_index=True, default=timezone.localdate)
    invoice_number = models.CharField('Número da NF', max_length=40, blank=True, default='')
    invoice_series = models.CharField('Série', max_length=20, blank=True, default='')
    channel = models.ForeignKey(SalesChannel, on_delete=models.PROTECT, verbose_name='Canal', null=True, blank=True)
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, verbose_name='Local de estoque', null=True, blank=True)
    products_amount = money('Valor dos produtos (R$)')
    discount = money('Desconto (R$)')
    shipping_received = money('Frete recebido (R$)')
    revenue_adjustment = models.DecimalField('Ajuste gerencial da receita (R$)', max_digits=18, decimal_places=2, default=0)
    revenue_adjustment_reason = models.CharField('Motivo do ajuste de receita', max_length=500, blank=True)
    shipping_paid = money('Frete pago (R$)')
    fees = money('Taxas (R$)')
    difal = money('DIFAL (R$)')
    commission = money('Comissão (R$)')
    other_costs = money('Outros custos variáveis (R$)')
    extra_costs_total = money('Total de taxas extras')
    tax_rule = models.ForeignKey(TaxRule, null=True, blank=True, on_delete=models.PROTECT, verbose_name='Regra tributária')
    tax_override = models.DecimalField('Imposto manual (R$)', max_digits=18, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    tax_reason = models.CharField('Motivo do imposto manual', max_length=500, blank=True)
    notes = models.TextField('Observação', blank=True, max_length=3000)
    status = models.CharField(max_length=12, choices=[('DRAFT','Rascunho'),('CONFIRMED','Confirmada'),('CANCELLED','Cancelada')], default='DRAFT', db_index=True)
    tax_snapshot = models.JSONField(default=dict, editable=False)
    tax_amount = money('Imposto aplicado')
    cmv = models.DecimalField(max_digits=24, decimal_places=6, default=0, editable=False)
    minimum_margin = models.DecimalField(max_digits=6, decimal_places=2, default=0, editable=False)
    stock_operation = models.OneToOneField(StockOperation, null=True, on_delete=models.PROTECT, related_name='sale_confirmation', editable=False)
    return_operation = models.OneToOneField(StockOperation, null=True, on_delete=models.PROTECT, related_name='sale_cancellation', editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_sales')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='confirmed_sales')
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='cancelled_sales')
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, editable=False)
    cancellation_reason = models.CharField(max_length=500, blank=True)
    external_id = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=40, default='manual')
    class Meta:
        ordering = ['-date','-pk']
        constraints = [models.UniqueConstraint(fields=['invoice_number','invoice_series'],condition=~models.Q(invoice_number=''),name='sales_unique_invoice'), models.CheckConstraint(condition=models.Q(discount__lte=models.F('products_amount')),name='sales_valid_discount'),
            models.CheckConstraint(condition=models.Q(products_amount__gte=models.F('discount')-models.F('shipping_received')-models.F('revenue_adjustment')), name='sales_nonnegative_revenue'),
            models.CheckConstraint(condition=models.Q(status='DRAFT') | models.Q(status='CANCELLED') | models.Q(channel__isnull=False, location__isnull=False), name='sales_confirmed_context')]
        indexes = [models.Index(fields=['channel','date'])]
    @property
    def revenue(self): return self.products_amount - self.discount + self.shipping_received + self.revenue_adjustment
    @property
    def reference(self): return f'NF {self.invoice_number}' if self.invoice_number else f'Venda #{self.pk} (sem NF)'
    @property
    def contribution(self): return self.revenue-self.cmv-self.shipping_paid-self.fees-self.tax_amount-self.difal-self.commission-self.other_costs-self.extra_costs_total
    @property
    def margin_percent(self): return self.contribution/self.revenue*100 if self.revenue else None
    @property
    def margin_label(self):
        if self.contribution < 0: return 'MARGEM NEGATIVA'
        if self.margin_percent is None: return 'SEM RECEITA'
        return 'ALERTA' if self.margin_percent < self.minimum_margin else 'POSITIVA'

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))])
    sku_snapshot = models.CharField(max_length=60, blank=True)
    name_snapshot = models.CharField(max_length=240, blank=True)
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    cmv = models.DecimalField(max_digits=24, decimal_places=6, default=0)
    class Meta:
        ordering = ['pk']
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0),name='sales_positive_quantity')]

class SaleConsumption(Immutable):
    item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name='consumptions')
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT)


class SaleExtraCost(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='extra_costs')
    name = models.CharField('Taxa / descrição', max_length=120)
    amount = money('Valor (R$)')
    class Meta:
        ordering = ['pk']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gte=0), name='sales_extra_nonnegative')]

class TaxRateChange(Immutable):
    rule = models.ForeignKey(TaxRule, on_delete=models.PROTECT, related_name='changes')
    effective_from = models.DateField('Usar a partir de')
    rate = models.DecimalField('Nova alíquota (%)', max_digits=7, decimal_places=4, validators=[MinValueValidator(0), MaxValueValidator(100)])
    base = models.CharField('Base de cálculo', max_length=20, choices=TaxRule._meta.get_field('base').choices)
    reason = models.CharField('Motivo', max_length=500)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-effective_from','-pk']
        indexes = [models.Index(fields=['rule','effective_from'])]
        constraints = [models.CheckConstraint(condition=models.Q(rate__gte=0,rate__lte=100),name='sales_changed_tax_rate_range')]

class SaleTaxRevision(Immutable):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='tax_revisions')
    change = models.ForeignKey(TaxRateChange, on_delete=models.PROTECT, related_name='revisions')
    before_amount = money('Imposto anterior')
    after_amount = money('Imposto recalculado')
    before_snapshot = models.JSONField()
    after_snapshot = models.JSONField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['sale','change'],name='sales_unique_tax_revision')]
