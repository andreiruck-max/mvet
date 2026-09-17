import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone


def money(label, default=0):
    return models.DecimalField(label, max_digits=18, decimal_places=2, default=default)


class FinancialAccount(models.Model):
    name = models.CharField('Nome', max_length=120, unique=True)
    institution = models.CharField('Instituição', max_length=120, blank=True)
    kind = models.CharField('Tipo', max_length=20, choices=[('BANK','Banco'),('WALLET','Carteira digital'),('CASH','Caixa'),('INVESTMENT','Investimento')])
    opening_balance = money('Saldo inicial (R$)')
    opening_date = models.DateField('Data do saldo inicial')
    active = models.BooleanField('Ativa', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name','pk']

    def __str__(self):
        return self.name


class FinancialTitle(models.Model):
    DIRECTIONS = [('PAY','Pagar'),('RECEIVE','Receber')]
    CATEGORIES = [('OPERATING','Operacional'),('FINANCIAL','Financeiro / juros'),('PRINCIPAL','Patrimonial / principal'),('OPENING','Pendência de abertura'),('OTHER','A classificar')]
    key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fingerprint = models.CharField(max_length=64, blank=True, editable=False)
    direction = models.CharField('Tipo', max_length=8, choices=DIRECTIONS)
    description = models.CharField('Descrição', max_length=240)
    counterparty = models.CharField('Favorecido / cliente', max_length=240, blank=True)
    date = models.DateField('Data de origem')
    due_date = models.DateField('Vencimento', db_index=True)
    amount = money('Valor principal (R$)')
    settled = money('Principal liquidado')
    account = models.ForeignKey(FinancialAccount, null=True, blank=True, on_delete=models.PROTECT, verbose_name='Conta prevista')
    category = models.CharField('Classificação gerencial', max_length=20, choices=CATEGORIES, default='OTHER')
    opening = models.BooleanField('Pendência anterior ao corte', default=False)
    notes = models.CharField('Observação', max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=[('OPEN','Aberto'),('CANCELLED','Cancelado')], default='OPEN')
    purchase_installment = models.OneToOneField('purchases.PurchaseInstallment', null=True, blank=True, on_delete=models.PROTECT, related_name='financial_title')
    sale = models.OneToOneField('sales.Sale', null=True, blank=True, on_delete=models.PROTECT, related_name='financial_title')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=30, default='manual')
    external_id = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['due_date','pk']
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0, settled__gte=0, settled__lte=models.F('amount')), name='finance_title_amounts'), models.CheckConstraint(condition=models.Q(purchase_installment__isnull=True)|models.Q(sale__isnull=True), name='finance_single_origin')]
        indexes = [models.Index(fields=['status','due_date'])]

    @property
    def remaining(self):
        return self.amount-self.settled

    @property
    def display_status(self):
        if self.status=='CANCELLED': return 'Cancelado'
        if not self.remaining: return 'Pago' if self.direction=='PAY' else 'Recebido'
        if self.due_date<timezone.localdate(): return 'Vencido (parcial)' if self.settled else 'Vencido'
        return 'Parcial' if self.settled else 'Pendente'


class FinancialOperation(models.Model):
    key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fingerprint = models.CharField(max_length=64)
    kind = models.CharField(max_length=12, choices=[('SETTLEMENT','Liquidação'),('TRANSFER','Transferência'),('REVERSAL','Estorno')])
    status = models.CharField(max_length=10, choices=[('POSTED','Realizado'),('PLANNED','Previsto'),('CANCELLED','Cancelado')], default='POSTED')
    date = models.DateField('Data', db_index=True)
    description = models.CharField('Descrição', max_length=500)
    title = models.ForeignKey(FinancialTitle, null=True, blank=True, on_delete=models.PROTECT, related_name='operations')
    principal = money('Principal baixado')
    interest = money('Juros / acréscimos')
    discount = money('Desconto / abatimento')
    actual = money('Valor efetivo')
    reversal_of = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversal')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date','-pk']
        constraints = [models.CheckConstraint(condition=models.Q(principal__gte=0,interest__gte=0,discount__gte=0,actual__gte=0), name='finance_operation_nonnegative')]


class FinancialEntry(models.Model):
    operation = models.ForeignKey(FinancialOperation, on_delete=models.PROTECT, related_name='entries')
    account = models.ForeignKey(FinancialAccount, on_delete=models.PROTECT, related_name='entries')
    amount = money('Valor com sinal')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['operation','account'], name='finance_one_leg_per_account'),models.CheckConstraint(condition=~models.Q(amount=0), name='finance_entry_nonzero')]
