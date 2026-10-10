import uuid
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from apps.inventory.models import Immutable

def money():
    return models.DecimalField(max_digits=18, decimal_places=2, default=0)

def rate(**kwargs):
    return models.DecimalField('Percentual (%)', max_digits=7, decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(100)], **kwargs)

class CommissionSettings(models.Model):
    default_rate = rate(default=0)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name='commission_single_settings'),
            models.CheckConstraint(condition=models.Q(default_rate__gte=0, default_rate__lte=100), name='commission_default_rate')]

class Payee(models.Model):
    name = models.CharField('Nome', max_length=180)
    kind = models.CharField('Tipo', max_length=20, choices=[('EMPLOYEE','Vendedor interno'),('REP','Representante'),('PARTNER','Parceiro comercial'),('OTHER','Outro')], default='EMPLOYEE')
    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name='Usuário para consulta (opcional)', null=True, blank=True, on_delete=models.PROTECT)
    default_rate = rate(null=True, blank=True)
    active = models.BooleanField('Ativo', default=True)
    class Meta:
        ordering = ['name','pk']
        constraints = [models.CheckConstraint(condition=models.Q(default_rate__isnull=True)|models.Q(default_rate__gte=0,default_rate__lte=100), name='commission_payee_rate')]
    def __str__(self): return self.name

class CommissionPlan(models.Model):
    sale = models.OneToOneField('sales.Sale', on_delete=models.PROTECT, related_name='commission_plan')
    payee = models.ForeignKey(Payee, on_delete=models.PROTECT, related_name='plans')
    customer = models.CharField('Cliente', max_length=240, blank=True)
    rate = rate()
    rate_source = models.CharField(max_length=20, choices=[('MANUAL','Manual na venda'),('PAYEE','Padrão do comissionado'),('DEFAULT','Padrão global')])
    base = money()
    total = money()
    override_total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cancelled = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(base__gte=0,total__gte=0,rate__gte=0,rate__lte=100), name='commission_plan_values')]

class Installment(models.Model):
    plan = models.ForeignKey(CommissionPlan, on_delete=models.PROTECT, related_name='installments')
    number = models.PositiveIntegerField()
    due_date = models.DateField()
    amount = money()
    forecast = money()
    class Meta:
        ordering = ['number','pk']
        constraints = [models.UniqueConstraint(fields=['plan','number'], name='commission_installment_number'),
            models.CheckConstraint(condition=models.Q(amount__gt=0,forecast__gte=0), name='commission_installment_values')]
    def __str__(self): return f'{self.plan.sale.reference} · parcela {self.number}'

class Command(Immutable):
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    fingerprint = models.CharField(max_length=64)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(max_length=24)
    reason = models.CharField(max_length=500)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)

class Entry(Immutable):
    installment = models.ForeignKey(Installment, on_delete=models.PROTECT, related_name='entries')
    command = models.ForeignKey(Command, on_delete=models.PROTECT, related_name='entries')
    date = models.DateField(db_index=True)
    received = money()
    released = money()
    reversal_of = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversal')
    terms = models.JSONField(default=dict)
    def save(self,*args,**kwargs):
        if self._state.adding:
            plan=self.installment.plan
            self.terms={'base':str(plan.base),'rate':str(plan.rate),'source':plan.rate_source,
                'total':str(plan.total),'installment_forecast':str(self.installment.forecast)}
        return super().save(*args,**kwargs)
    class Meta:
        ordering = ['date','pk']
        constraints = [models.CheckConstraint(condition=~models.Q(received=0,released=0),name='commission_entry_nonzero')]

class Payment(Immutable):
    payee = models.ForeignKey(Payee, on_delete=models.PROTECT, related_name='payments')
    command = models.OneToOneField(Command, on_delete=models.PROTECT, related_name='payment')
    date = models.DateField(db_index=True)
    period = models.DateField()
    amount = money()
    method = models.CharField('Forma de pagamento', max_length=100)
    reversal_of = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversal')
    class Meta:
        ordering = ['-date','-pk']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0,reversal_of__isnull=True)|models.Q(amount__lt=0,reversal_of__isnull=False),name='commission_payment_sign')]

class Allocation(Immutable):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='allocations')
    entry = models.ForeignKey(Entry, on_delete=models.PROTECT, related_name='allocations')
    amount = money()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['payment','entry'], name='commission_payment_entry'),
            models.CheckConstraint(condition=~models.Q(amount=0),name='commission_allocation_nonzero')]
