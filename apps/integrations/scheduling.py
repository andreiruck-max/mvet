"""Durable read-only invoice polling, isolated from HTTP and financial confirmation."""
from datetime import date, timedelta
from django import forms
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from apps.accounts.access import master
from apps.core.services import audit
from .models import BlingSchedule, BlingConnection
from . import bling

LOCK_ID = 7319056
STATUSES = {'SALE': (56,), 'PURCHASE': (5, 7)}


class ScheduleForm(forms.ModelForm):
    interval_hours = forms.IntegerField(label='Intervalo (horas)', min_value=1, max_value=168)
    lookback_days = forms.IntegerField(label='Reconsultar últimos (dias)', min_value=1, max_value=366)

    class Meta:
        model = BlingSchedule
        fields = ['enabled', 'interval_hours', 'lookback_days']


@transaction.atomic
def configure(*, actor, kind, data):
    master(actor)
    if kind not in STATUSES:
        raise ValidationError('Tipo de consulta inválido.')
    obj, _ = BlingSchedule.objects.get_or_create(kind=kind)
    obj = BlingSchedule.objects.select_for_update().get(pk=obj.pk)
    form = ScheduleForm(data, instance=obj)
    if not form.is_valid():
        raise ValidationError('Confira o intervalo (1 a 168 horas) e o período (1 a 366 dias).')
    if form.cleaned_data['enabled']:
        if not BlingConnection.objects.filter(pk=1).exclude(tokens='').exists():
            raise ValidationError('Autorize a conexão Bling antes de ativar a busca automática.')
    obj = form.save(commit=False)
    obj.actor = actor
    obj.revision += 1
    obj.cursor = {}
    obj.next_run_at = timezone.now() if obj.enabled else None
    obj.message = 'Aguardando o serviço em segundo plano.' if obj.enabled else 'Busca automática desativada.'
    obj.save()
    audit(actor, obj, 'bling_schedule_configured', after={
        'kind': kind, 'enabled': obj.enabled, 'interval_hours': obj.interval_hours,
        'lookback_days': obj.lookback_days})
    return obj


def tick():
    """At most one page per tick; session lock is released on process/DB disconnect."""
    for kind in STATUSES:
        BlingSchedule.objects.get_or_create(kind=kind)
    with connection.cursor() as db:
        db.execute('SELECT pg_try_advisory_lock(%s)', [LOCK_ID])
        acquired = db.fetchone()[0]
    if not acquired:
        return False
    try:
        now = timezone.now()
        BlingSchedule.objects.update(last_worker_seen=now)
        obj = BlingSchedule.objects.filter(enabled=True).filter(
            Q(next_run_at__isnull=True) | Q(next_run_at__lte=now)).order_by('next_run_at', 'pk').first()
        if obj is None:
            return False
        process_page(obj)
        return True
    finally:
        with connection.cursor() as db:
            db.execute('SELECT pg_advisory_unlock(%s)', [LOCK_ID])


def process_page(obj):
    now = timezone.now()
    update = BlingSchedule.objects.filter(pk=obj.pk, revision=obj.revision, enabled=True)
    cursor = obj.cursor
    if not cursor:
        today = timezone.localdate()
        cursor = {'start': str(today-timedelta(days=obj.lookback_days-1)), 'end': str(today), 'status': 0, 'page': 1}
        obj.processed = obj.errors = 0
        update.update(cursor=cursor, processed=0, errors=0, last_started_at=now,
                      message='Consultando em segundo plano.')
    try:
        # Fetch a fresh user each page: revoked access stops the next request.
        from django.contrib.auth import get_user_model
        actor = get_user_model().objects.filter(pk=obj.actor_id, is_active=True).first()
        if not actor:
            raise PermissionDenied
        run = bling.sync_page(actor=actor, kind=obj.kind, start=date.fromisoformat(cursor['start']),
            end=date.fromisoformat(cursor['end']), page=cursor['page'],
            source_status=STATUSES[obj.kind][cursor['status']], time_budget=300)
        if run.message:
            update.update(next_run_at=now+timedelta(minutes=5), message=run.message,
                          errors=obj.errors+run.errors)
            return
        obj.processed += run.processed
        obj.errors += run.errors
        if run.has_more:
            if cursor['page'] >= 10000:
                raise ValidationError('Limite de páginas atingido. Reduza o período da busca automática.')
            cursor['page'] += 1
        else:
            cursor['status'] += 1
            cursor['page'] = 1
        finished = cursor['status'] >= len(STATUSES[obj.kind])
        update.update(cursor={} if finished else cursor, processed=obj.processed, errors=obj.errors,
            next_run_at=timezone.now()+timedelta(hours=obj.interval_hours) if finished else timezone.now()+timedelta(seconds=10),
            last_finished_at=timezone.now() if finished else obj.last_finished_at,
            message=('Consulta concluída. Confira as notas e eventuais erros na fila.' if finished else 'Consultando em segundo plano.'))
    except PermissionDenied:
        update.update(enabled=False, message='Busca pausada: responsável sem acesso. Salve a configuração com um administrador autorizado.')
    except ValidationError as exc:
        update.update(next_run_at=timezone.now()+timedelta(minutes=5), message='; '.join(exc.messages)[:500])
