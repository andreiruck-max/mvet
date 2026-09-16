import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from apps.products.models import NamedActive, Product

class StockLocation(NamedActive): pass

class StockBalance(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='balances')
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['product','location'], name='unique_stock_location'), models.CheckConstraint(condition=Q(quantity__gte=0), name='stock_nonnegative')]

class Immutable(models.Model):
    class Meta: abstract = True
    def save(self,*args,**kwargs):
        if not self._state.adding: raise ValidationError('Registro imutável. Utilize estorno.')
        return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs): raise ValidationError('Registro imutável. Utilize estorno.')

class StockOperation(Immutable):
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    fingerprint = models.CharField(max_length=64)
    kind = models.CharField(max_length=20, choices=[('OPENING','Saldo inicial'),('RECEIPT','Entrada'),('ISSUE','Saída'),('ADJUST_IN','Ajuste: acréscimo'),('ADJUST_OUT','Ajuste: redução'),('TRANSFER','Transferência'),('SPLIT','Fracionamento'),('KIT_ISSUE','Saída de kit'),('REVALUE','Correção de custo'),('REVERSAL','Estorno'),('SALE_OUT','Venda'),('SALE_RETURN','Cancelamento de venda')])
    date = models.DateField(db_index=True)
    reason = models.CharField(max_length=500)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    reversal_of = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversal')
    class Meta: ordering = ['-pk']

class StockMovement(Immutable):
    operation = models.ForeignKey(StockOperation, on_delete=models.PROTECT, related_name='movements')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='movements')
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    value = models.DecimalField(max_digits=24, decimal_places=6)
    unit_cost = models.DecimalField(max_digits=24, decimal_places=6)
    before_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    after_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    before_value = models.DecimalField(max_digits=24, decimal_places=6)
    after_value = models.DecimalField(max_digits=24, decimal_places=6)
    before_average = models.DecimalField(max_digits=24, decimal_places=6)
    after_average = models.DecimalField(max_digits=24, decimal_places=6)
    class Meta:
        ordering = ['pk']
        indexes = [models.Index(fields=['product','operation'])]

class OpeningImport(models.Model):
    digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    report = models.JSONField(default=dict)
