import hashlib
import json
import re
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from apps.core.services import audit, require
from .models import AlertConfiguration, BackupEvidence, Notification, NotificationPreference, NotificationRead
from .selectors import allowed_kinds, visible


def notification_lock():
    # Independent from stock/cash locks: notification failures cannot undo sales.
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [763820108])


def conditions(config, now):
    from apps.products.models import Product
    from apps.sales.models import Sale
    from apps.finance.models import FinancialTitle
    today = timezone.localdate(now)
    if config.stock:
        for p in Product.objects.filter(active=True, kind='SIMPLE', minimum__gt=0, quantity__lte=F('minimum')).iterator():
            yield 'STOCK', p.pk, f'Estoque mínimo: {p.sku}', f'{p.name}: {p.quantity} {p.unit} no total dos estoques; mínimo {p.minimum}.', 'WARNING'
    if config.margin:
        for sale in Sale.objects.filter(status='CONFIRMED').iterator():
            if sale.margin_label not in ('ALERTA', 'MARGEM NEGATIVA'):
                continue
            percent = f'{sale.margin_percent:.2f}%' if sale.margin_percent is not None else 'sem percentual (receita zero)'
            yield 'MARGIN', sale.pk, f'NF {sale.invoice_number}: {sale.margin_label.lower()}', f'Série {sale.invoice_series or "única"} · contribuição R$ {sale.contribution:.2f} · {percent}. Limite da venda: {sale.minimum_margin}%.', 'CRITICAL' if sale.contribution < 0 else 'WARNING'
    if config.due:
        for title in FinancialTitle.objects.filter(status='OPEN', amount__gt=F('settled'), due_date__lte=today+timedelta(days=config.due_days)).iterator():
            days = (title.due_date-today).days
            label = 'vencida' if days < 0 else ('vence hoje' if days == 0 else 'a vencer')
            yield 'DUE', title.pk, f'Conta {title.get_direction_display().lower()} · {label}', f'{title.description} · vencimento {title.due_date:%d/%m/%Y} · saldo R$ {title.remaining:.2f}.', 'CRITICAL' if days < 0 else ('WARNING' if days == 0 else 'INFO')
    if config.backup:
        last = BackupEvidence.objects.first()
        success = BackupEvidence.objects.filter(success=True).first()
        since = success.occurred_at if success else config.backup_started_at
        if last and not last.success:
            yield 'BACKUP', 1, 'Falha na execução do backup', f'Falha registrada em {timezone.localtime(last.occurred_at):%d/%m/%Y %H:%M}. Confira o processo de backup.', 'CRITICAL'
        elif since and now-since > timedelta(hours=config.backup_hours):
            yield 'BACKUP', 1, 'Backup sem confirmação recente', f'Nenhum sucesso registrado nas últimas {config.backup_hours} horas. Verifique o agendamento e os arquivos.', 'CRITICAL'


@transaction.atomic
def refresh():
    notification_lock()
    config, _ = AlertConfiguration.objects.get_or_create(pk=1)
    now = timezone.now()
    seen = []
    for kind, entity_id, title, description, severity in conditions(config, now):
        fingerprint = hashlib.sha256(json.dumps([title, description, severity], ensure_ascii=False).encode()).hexdigest()
        obj, created = Notification.objects.get_or_create(kind=kind, entity_id=entity_id,
            defaults=dict(title=title, description=description, severity=severity, fingerprint=fingerprint))
        if not created and (not obj.active or obj.fingerprint != fingerprint):
            obj.title, obj.description, obj.severity, obj.fingerprint = title, description, severity, fingerprint
            obj.revision += 1
            obj.active, obj.resolved_at = True, None
            obj.save()
        seen.append(obj.pk)
    Notification.objects.filter(active=True).exclude(pk__in=seen).update(active=False, resolved_at=now, updated_at=now)
    config.last_refresh = now
    config.save(update_fields=['last_refresh'])
    return len(seen)


@transaction.atomic
def mark_read(*, actor, pk, revision):
    notification_lock()
    obj = get_object_or_404(visible(actor), pk=pk, revision=revision)
    NotificationRead.objects.update_or_create(notification=obj, user=actor, defaults={'revision': obj.revision})


@transaction.atomic
def preferences(*, actor, enabled):
    notification_lock()
    for kind in allowed_kinds(actor):
        obj, _ = NotificationPreference.objects.get_or_create(user=actor, kind=kind)
        before = obj.enabled
        obj.enabled = kind in enabled
        if before != obj.enabled:
            obj.save(update_fields=['enabled'])
            audit(actor, obj, 'notification_preference', {'enabled': before}, {'enabled': obj.enabled})


@transaction.atomic
def configure(*, actor, data):
    require(actor, 'core.manage_configuration')
    notification_lock()
    obj, _ = AlertConfiguration.objects.get_or_create(pk=1)
    fields = ('stock', 'margin', 'due', 'due_days', 'backup', 'backup_hours')
    before = {k: getattr(obj, k) for k in fields}
    for key in fields:
        setattr(obj, key, data[key])
    if obj.backup and not before['backup']:
        obj.backup_started_at = timezone.now()
    obj.full_clean()
    obj.save()
    audit(actor, obj, 'notification_configuration', before, {k: getattr(obj, k) for k in fields})
    return obj


@transaction.atomic
def record_backup(*, success, size_bytes=0, sha256=''):
    if success and (size_bytes <= 0 or not re.fullmatch('[0-9a-f]{64}', sha256)):
        raise ValidationError('Sucesso exige tamanho positivo e SHA-256 do arquivo validado.')
    if not success and (size_bytes or sha256):
        raise ValidationError('Falha não deve registrar evidência de sucesso.')
    return BackupEvidence.objects.create(success=success, size_bytes=size_bytes, sha256=sha256)
