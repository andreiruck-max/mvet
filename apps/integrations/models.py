from django.utils import timezone
from django.conf import settings
from django.db import models


class BlingStockCorrection(models.Model):
    """Durable intent; remote calls may succeed even when their response is lost."""
    key = models.UUIDField(unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    snapshot = models.JSONField()
    field = models.CharField(max_length=10)
    direction = models.CharField(max_length=10)
    reason = models.CharField(max_length=350)
    status = models.CharField(max_length=12, default='PENDING', choices=[('PENDING', 'Em execução'), ('DONE', 'Concluída'), ('FAILED', 'Não aplicada'), ('UNKNOWN', 'Conferir no Bling'), ('REVIEWED', 'Conferida manualmente')])
    message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)


class BlingConnection(models.Model):
    """One local company. Secrets encrypted with a separate environment key."""
    issuer = models.CharField(max_length=14, unique=True)
    tokens = models.TextField(blank=True, editable=False)
    expires_at = models.DateTimeField(null=True, editable=False)
    last_request_at = models.DateTimeField(null=True, editable=False)
    last_sync_at = models.DateTimeField(null=True, editable=False)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name='single_bling_connection')]


class InvoiceImport(models.Model):
    connection = models.ForeignKey(BlingConnection, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=40)
    access_key = models.CharField(max_length=44, blank=True)
    number = models.CharField(max_length=30)
    series = models.CharField(max_length=10, blank=True)
    issued_on = models.DateField(null=True)
    source_status = models.CharField(max_length=20, blank=True)
    # Allowlisted commercial fields only: never retain costs, tokens or contact PII.
    source = models.JSONField(default=dict)
    approved_source = models.JSONField(default=dict, editable=False)
    review_overrides = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, default='PENDING', choices=[
        ('PENDING', 'Pendente'), ('IMPORTED', 'Importada'),
        ('IGNORED', 'Ignorada'), ('ERROR', 'Com erro')])
    error = models.CharField(max_length=500, blank=True)
    discrepancy = models.BooleanField(default=False)
    sale = models.OneToOneField('sales.Sale', null=True, blank=True, on_delete=models.PROTECT, related_name='bling_import')
    created_at = models.DateTimeField(auto_now_add=True)
    checked_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-issued_on', '-pk']
        indexes = [models.Index(fields=['status', 'issued_on'])]
        constraints = [
            models.CheckConstraint(condition=(models.Q(status='IMPORTED', sale__isnull=False) | (~models.Q(status='IMPORTED') & models.Q(sale__isnull=True))), name='bling_sale_status_consistent'),
            models.UniqueConstraint(fields=['connection', 'external_id'], name='bling_unique_invoice'),
            models.UniqueConstraint(fields=['access_key'], condition=~models.Q(access_key=''), name='bling_unique_key'),
        ]


class ProductAlias(models.Model):
    connection = models.ForeignKey(BlingConnection, on_delete=models.PROTECT)
    code = models.CharField(max_length=120)
    unit = models.CharField(max_length=12)
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['connection', 'code', 'unit'], name='bling_unique_alias')]


class ImportRun(models.Model):
    kind = models.CharField(max_length=8, default="SALE", choices=[("SALE", "Vendas"), ("PURCHASE", "Compras")])
    connection = models.ForeignKey(BlingConnection, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    start = models.DateField()
    end = models.DateField()
    page = models.PositiveIntegerField()
    source_status = models.PositiveIntegerField(default=5)
    processed = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)
    has_more = models.BooleanField(default=False)
    message = models.CharField(max_length=500, blank=True)
    error_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    class Meta:
        ordering = ['-pk']


class ReviewDefaults(models.Model):
    full_store = models.CharField('Loja externa Full', max_length=40)
    full_channel = models.ForeignKey('sales.SalesChannel', on_delete=models.PROTECT, related_name='+', verbose_name='Canal Full')
    full_location = models.ForeignKey('inventory.StockLocation', on_delete=models.PROTECT, related_name='+', verbose_name='Estoque Full')
    default_channel = models.ForeignKey('sales.SalesChannel', on_delete=models.PROTECT, related_name='+', verbose_name='Canal Mercadovet / demais lojas')
    default_location = models.ForeignKey('inventory.StockLocation', on_delete=models.PROTECT, related_name='+', verbose_name='Estoque Mercadovet / demais lojas')

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name='single_bling_review_defaults')]


class PurchaseInvoiceImport(models.Model):
    connection = models.ForeignKey(BlingConnection, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=40)
    access_key = models.CharField(max_length=44, unique=True)
    number = models.CharField(max_length=30)
    series = models.CharField(max_length=10)
    issued_on = models.DateField()
    source = models.JSONField(default=dict)
    approved_source = models.JSONField(default=dict, editable=False)
    review_overrides = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=1)
    error = models.CharField(max_length=500, blank=True)
    discrepancy = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    purchase = models.OneToOneField('purchases.Purchase', null=True, blank=True, on_delete=models.PROTECT, related_name='bling_import')
    checked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issued_on', '-pk']
        constraints = [models.UniqueConstraint(fields=['connection', 'external_id'], name='bling_unique_purchase_invoice')]


class BlingComparisonCache(models.Model):
    """Last consulted page per master; never an authority for writes."""
    actor = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    payload = models.JSONField(default=dict)


class BlingSchedule(models.Model):
    kind = models.CharField(max_length=8, unique=True, choices=[('SALE', 'Vendas'), ('PURCHASE', 'Compras')])
    enabled = models.BooleanField('Ativar busca automática', default=False)
    interval_hours = models.PositiveSmallIntegerField('Intervalo (horas)', default=1)
    lookback_days = models.PositiveSmallIntegerField('Reconsultar últimos (dias)', default=7)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField(default=0)
    next_run_at = models.DateTimeField(null=True)
    last_started_at = models.DateTimeField(null=True)
    last_finished_at = models.DateTimeField(null=True)
    last_worker_seen = models.DateTimeField(null=True)
    cursor = models.JSONField(default=dict, editable=False)
    message = models.CharField(max_length=500, blank=True)
    processed = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)

    @property
    def worker_online(self):
        from datetime import timedelta
        from django.utils import timezone
        return bool(self.last_worker_seen and self.last_worker_seen > timezone.now()-timedelta(minutes=10))

    class Meta:
        ordering = ['kind']
        constraints = [
            models.CheckConstraint(condition=models.Q(kind__in=['SALE', 'PURCHASE']), name='bling_schedule_kind'),
            models.CheckConstraint(condition=models.Q(interval_hours__gte=1, interval_hours__lte=168), name='bling_schedule_interval'),
            models.CheckConstraint(condition=models.Q(lookback_days__gte=1, lookback_days__lte=366), name='bling_schedule_lookback'),
        ]


class BlingBankAccount(models.Model):
    connection = models.ForeignKey(BlingConnection, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=40)
    description = models.CharField(max_length=240)

    class Meta:
        ordering = ['description', 'pk']
        constraints = [models.UniqueConstraint(fields=['connection', 'external_id'], name='bling_bank_account_identity')]

    def __str__(self):
        return f'{self.description} · {self.external_id}'


class BlingBankLink(models.Model):
    account = models.OneToOneField('finance.FinancialAccount', on_delete=models.PROTECT, related_name='bling_bank')
    external = models.OneToOneField(BlingBankAccount, on_delete=models.PROTECT)
    start_date = models.DateField('Data inicial da comparação')
    opening_balance = models.DecimalField('Saldo Bling antes dos movimentos dessa data (R$)', max_digits=18, decimal_places=2, null=True, blank=True)
    automatic = models.BooleanField('Atualizar ao abrir a conta', default=True)
    requested_through = models.DateField(null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class BlingBankRun(models.Model):
    link = models.ForeignKey(BlingBankLink, on_delete=models.PROTECT, related_name='runs')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    start = models.DateField()
    end = models.DateField()
    status = models.CharField(max_length=10, default='QUEUED', choices=[('QUEUED','Aguardando'),('RUNNING','Atualizando'),('DONE','Concluída'),('FAILED','Falhou')])
    phase = models.CharField(max_length=1, default='R')
    page = models.PositiveIntegerField(default=1)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    message = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['link'], condition=models.Q(status__in=['QUEUED','RUNNING']), name='bling_bank_one_active_run')]


class BlingBankStaging(models.Model):
    run = models.ForeignKey(BlingBankRun, on_delete=models.CASCADE, related_name='staged')
    external_id = models.CharField(max_length=40)
    data = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run','external_id'], name='bling_bank_stage_identity')]


class BlingBankEntry(models.Model):
    link = models.ForeignKey(BlingBankLink, on_delete=models.PROTECT, related_name='entries')
    external_id = models.CharField(max_length=40)
    date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    description = models.CharField(max_length=1000, blank=True)
    counterparty = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)
    source_type = models.CharField(max_length=80, blank=True)
    source_id = models.CharField(max_length=40, blank=True)
    deleted = models.BooleanField(default=False)
    present = models.BooleanField(default=True)
    checked_at = models.DateTimeField()

    class Meta:
        ordering = ['-date','-external_id']
        constraints = [models.UniqueConstraint(fields=['link','external_id'], name='bling_bank_entry_identity')]


class BlingBankDay(models.Model):
    link = models.ForeignKey(BlingBankLink, on_delete=models.PROTECT, related_name='days')
    date = models.DateField()
    checked_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['link','date'], name='bling_bank_day_identity')]
