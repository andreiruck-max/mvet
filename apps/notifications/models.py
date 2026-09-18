from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

KINDS = [('STOCK', 'Estoque mínimo'), ('MARGIN', 'Margem de venda'),
         ('DUE', 'Contas a pagar e receber'), ('BACKUP', 'Backup')]


class Notification(models.Model):
    kind = models.CharField(max_length=10, choices=KINDS)
    entity_id = models.PositiveBigIntegerField()
    title = models.CharField(max_length=260)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=[('INFO', 'Informação'), ('WARNING', 'Atenção'), ('CRITICAL', 'Crítico')])
    fingerprint = models.CharField(max_length=64)
    revision = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['-updated_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['kind', 'entity_id'], name='notification_condition_unique')]
        indexes = [models.Index(fields=['kind', 'active', '-updated_at'])]


class NotificationRead(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    revision = models.PositiveIntegerField()
    read_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['notification', 'user'], name='notification_read_unique')]


class NotificationPreference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, choices=KINDS)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'kind'], name='notification_preference_unique')]


class AlertConfiguration(models.Model):
    # Singleton created by migration; no admin editing bypass.
    stock = models.BooleanField('Estoque mínimo', default=True)
    margin = models.BooleanField('Margem baixa ou negativa', default=True)
    due = models.BooleanField('Contas a pagar e receber', default=True)
    due_days = models.PositiveSmallIntegerField('Antecedência em dias', default=3, validators=[MaxValueValidator(90)])
    backup = models.BooleanField('Monitorar backup', default=False)
    backup_hours = models.PositiveSmallIntegerField('Prazo máximo sem backup (horas)', default=36, validators=[MinValueValidator(1), MaxValueValidator(720)])
    backup_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_refresh = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(pk=1), name='alert_configuration_singleton'),
                       models.CheckConstraint(condition=models.Q(due_days__lte=90, backup_hours__gte=1, backup_hours__lte=720), name='alert_configuration_limits')]


class BackupEvidence(models.Model):
    occurred_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField()
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ['-occurred_at', '-pk']
        constraints = [models.CheckConstraint(condition=models.Q(success=False, size_bytes=0, sha256='') | (models.Q(success=True, size_bytes__gt=0) & ~models.Q(sha256='')), name='backup_evidence_content')]
