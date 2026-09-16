from decimal import Decimal
from django.db import models
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
    minimum = models.DecimalField('Estoque mínimo', max_digits=18, decimal_places=4, default=0)
    active = models.BooleanField('Ativo', default=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0, editable=False)
    value = models.DecimalField(max_digits=24, decimal_places=6, default=0, editable=False)
    average_cost = models.DecimalField(max_digits=24, decimal_places=6, default=0, editable=False)
    class Meta:
        ordering = ['name','pk']
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=0, value__gte=0, average_cost__gte=0, minimum__gte=0), name='product_nonnegative')]
    def __str__(self): return f'{self.sku} · {self.name}'

class ProductComposition(models.Model):
    kit = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='components')
    component = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='used_in')
    quantity = models.DecimalField('Quantidade', max_digits=18, decimal_places=4)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['kit','component'], name='unique_component'), models.CheckConstraint(condition=Q(quantity__gt=0) & ~Q(kit=models.F('component')), name='valid_component')]
