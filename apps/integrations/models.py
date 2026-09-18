from django.conf import settings
from django.db import models


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
