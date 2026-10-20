from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.db.models import Q

class NamedActive(models.Model):
    name = models.CharField('Nome', max_length=120, unique=True)
    active = models.BooleanField('Ativo', default=True)
    class Meta:
        abstract = True
        ordering = ['name']
    def __str__(self): return self.name

class Brand(NamedActive): pass
class ProductCategory(NamedActive): pass

class Product(models.Model):
    sku = models.CharField('SKU', max_length=60, unique=True)
    name = models.CharField('Produto', max_length=240, db_index=True)
    unit = models.CharField('Unidade', max_length=12, default='UN')
    kind = models.CharField('Tipo', max_length=10, choices=[('SIMPLE','Produto'),('KIT','Kit virtual')], default='SIMPLE')
    brand = models.ForeignKey(Brand, verbose_name='Marca', null=True, blank=True, on_delete=models.PROTECT)
    category = models.ForeignKey(ProductCategory, verbose_name='Categoria', null=True, blank=True, on_delete=models.PROTECT)
    markup = models.DecimalField('Markup individual (%)', max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)], help_text='Vazio utiliza o percentual geral definido pelo master.')
    fixed_sale_price = models.DecimalField('Preço de venda fixo', max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    minimum = models.DecimalField('Estoque mínimo', max_digits=18, decimal_places=4, default=0)
    active = models.BooleanField('Ativo', default=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0, editable=False)
    value = models.DecimalField(max_digits=24, decimal_places=6, default=0, editable=False)
    average_cost = models.DecimalField(max_digits=24, decimal_places=6, default=0, editable=False)
    class Meta:
        ordering = ['name','pk']
        constraints = [models.CheckConstraint(condition=Q(fixed_sale_price__isnull=True) | Q(fixed_sale_price__gte=0), name="product_fixed_price_nonnegative"), models.CheckConstraint(condition=Q(markup__isnull=True) | Q(markup__gte=0), name="product_markup_nonnegative"), models.CheckConstraint(condition=Q(average_cost__gte=0, minimum__gte=0), name='product_cost_minimum_nonnegative')]
    def __str__(self): return f'{self.sku} · {self.name}'

class ProductComposition(models.Model):
    kit = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='components')
    component = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='used_in')
    quantity = models.DecimalField('Quantidade', max_digits=18, decimal_places=4)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['kit','component'], name='unique_component'), models.CheckConstraint(condition=Q(quantity__gt=0) & ~Q(kit=models.F('component')), name='valid_component')]
