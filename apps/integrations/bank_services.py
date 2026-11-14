"""Read-only Bling statement mirror. No writes to either financial ledger."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone
from apps.accounts.access import master
from apps.core.services import audit, require
from apps.finance.models import FinancialAccount, FinancialEntry
from . import bling
from .models import (BlingConnection, BlingBankAccount, BlingBankLink, BlingBankRun,
                     BlingBankStaging, BlingBankEntry, BlingBankDay)

LOCK_ID = 7319057
ZERO = Decimal('0.00')
ACTIVE = ['QUEUED', 'RUNNING']


def access(actor):
    require(actor, 'core.view_finance')
    require(actor, 'core.fetch_bling')


def identifier(value):
    value = str(value)
    if not value.isascii() or not value.isdecimal() or not 0 < int(value) < 10**40:
        raise ValidationError('Identificador financeiro inválido recebido do Bling.')
    return str(int(value))


def rows(response):
    result = response.get('data') if isinstance(response, dict) else None
    if not isinstance(result, list) or len(result) > 1000:
        raise ValidationError('Lista financeira inválida recebida do Bling.')
    return result


def fetch_accounts(*, actor, page):
    master(actor)
    if not 1 <= page <= 1000:
        raise ValidationError('Página inválida.')
    conn = BlingConnection.objects.filter(pk=1).first()
    if not conn or not conn.tokens:
        raise ValidationError('Conecte o Bling antes de consultar as contas.')
    data = rows(bling.read('/contas-contabeis?' + urlencode(dict(pagina=page, limite=100,
        ocultarInvisiveis='false', ocultarTipoContaBancaria='false'))))
    normalized = []
    for row in data:
        if not isinstance(row, dict) or not isinstance(row.get('descricao'), str):
            raise ValidationError('Conta financeira inválida recebida do Bling.')
        normalized.append((identifier(row.get('id')), row['descricao'][:240]))
    with transaction.atomic():
        for external_id, description in normalized:
            BlingBankAccount.objects.update_or_create(connection=conn, external_id=external_id,
                defaults={'description': description})
    return bool(data)


@transaction.atomic
def configure(*, actor, account_id, external, start_date, opening_balance, automatic):
    master(actor)
    account = FinancialAccount.objects.select_for_update().get(pk=account_id)
    if start_date < account.opening_date or start_date > timezone.localdate():
        raise ValidationError('A data inicial deve estar entre a abertura da conta MVet e hoje.')
    obj = BlingBankLink.objects.select_for_update().filter(account=account).first()
    if obj and obj.external_id != external.pk:
        raise ValidationError('O vínculo com o Bling não pode ser trocado: o histórico importado pertence à conta original.')
    if BlingBankLink.objects.filter(external=external).exclude(account=account).exists():
        raise ValidationError('Esta conta Bling já está vinculada a outra conta MVet.')
    before = {} if obj is None else {'start_date': str(obj.start_date), 'opening_balance': str(obj.opening_balance), 'automatic': obj.automatic}
    if obj is None:
        obj = BlingBankLink(account=account, external=external)
    obj.start_date, obj.opening_balance, obj.automatic, obj.actor = start_date, opening_balance, automatic, actor
    obj.full_clean(); obj.save()
    audit(actor, obj, 'bling_bank_configured', before=before, after={
        'external': external.external_id, 'start_date': str(start_date),
        'opening_balance': str(opening_balance), 'automatic': automatic})
    return obj


@transaction.atomic
def enqueue(*, actor, link_id, start=None, end=None, automatic=False):
    access(actor)
    obj = BlingBankLink.objects.select_for_update().get(pk=link_id)
    if automatic and not obj.automatic:
        return None
    today = timezone.localdate()
    if automatic:
        obj.requested_through = today
        obj.save(update_fields=['requested_through'])
    # Reuse a pending request when several tabs/users open the same account.
    active = obj.runs.filter(status__in=ACTIVE).first()
    if active:
        if not automatic and (start is None or end is None or start < active.start or end > active.end):
            raise ValidationError('Já existe uma consulta em andamento para outro período. Aguarde sua conclusão e atualize o período desejado.')
        return active
    today = timezone.localdate()
    if automatic:
        # Also fill days without visits, but never repeatedly download all history.
        last = obj.days.order_by('-date').first()
        start = max(obj.start_date, min(last.date if last else obj.start_date, today))
        end = min(today, start + timedelta(days=365))
    if start is None or end is None or start > end or end > today or start < obj.account.opening_date or (end-start).days > 365:
        raise ValidationError('Escolha até 366 dias, entre a abertura da conta MVet e hoje.')
    run = BlingBankRun.objects.create(link=obj, actor=actor, start=start, end=end)
    audit(actor, run, 'bling_bank_requested', after={'start': str(start), 'end': str(end), 'automatic': automatic})
    return run


def parse_entry(row, run):
    """Normalize API scalars, retaining strict account/range/precision checks."""
    field = 'estrutura'
    try:
        field = 'id'; ext = identifier(row['id'])
        field = 'contaFinanceira.id'
        if identifier(row['contaFinanceira']['id']) != run.link.external.external_id:
            raise ValueError
        field = 'data'
        raw_date = row['data']
        # Some financial responses contain an ISO time suffix. Preserve calendar
        # date supplied by Bling rather than converting it through UTC.
        from datetime import datetime
        if not isinstance(raw_date,str):raise ValueError
        if len(raw_date)>10:
            datetime.fromisoformat(raw_date.replace('Z','+00:00'))
        day = date.fromisoformat(raw_date[:10])
        if not run.start <= day <= run.end:raise ValueError
        field = 'debCred'; direction = row['debCred']
        if direction not in ('D','C'):raise ValueError
        field = 'situacao'; state = row['situacao']
        if state != run.phase:raise ValueError
        field = 'valor'; raw_value=row['valor']
        if isinstance(raw_value,bool):raise ValueError
        value = Decimal(str(raw_value))
        # Debit values can already carry a minus sign; debCred is authoritative.
        if not value.is_finite() or abs(value) >= 10**16:raise ValueError
        rounded=value.quantize(Decimal('.01'))
        if value != rounded:
            if not isinstance(raw_value,float) or abs(value-rounded)>Decimal('0.000000001'):raise ValueError
            value=rounded
        value = -abs(value) if direction == 'D' else abs(value)
        def text(value, limit):
            if value is None: return ''
            if not isinstance(value, str): raise ValueError
            return value[:limit]
        field = 'origem'; origin = row.get('origem') or {}
        source_type=text(origin.get('tipo'),80)
        field = 'descricao'; description=text(row.get('descricao'),1000)
        field = 'observacoes'; notes=text(row.get('observacoes'),10000)
        field = 'contato.nome'; counterparty=text((row.get('contato') or {}).get('nome'),240)
        return ext, dict(date=str(day), amount=str(value), deleted=state == 'E',
            description=description, notes=notes, counterparty=counterparty,
            source_type=source_type, source_id=str(origin.get('id') or '')[:40])
    except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError, ValidationError):
        # Report only field and page, never raw financial data or credentials.
        raise ValidationError(f'Lançamento Bling inválido: campo {field}, página {run.page}, situação {run.phase}. Conta, período e precisão precisam corresponder à consulta. O extrato anterior foi preservado.') from None


def tick():
    with connection.cursor() as db:
        db.execute('SELECT pg_try_advisory_lock(%s)', [LOCK_ID])
        locked = db.fetchone()[0]
    if not locked: return False
    try:
        run = BlingBankRun.objects.filter(status__in=ACTIVE, next_attempt__lte=timezone.now()).select_related(
            'actor', 'link__external', 'link__account').order_by('next_attempt','pk').first()
        if not run: return False
        process_page(run)
        return True
    finally:
        with connection.cursor() as db:
            db.execute('SELECT pg_advisory_unlock(%s)', [LOCK_ID])


def process_page(run):
    if run.status not in ACTIVE: return
    try:
        access(run.actor)
        BlingBankRun.objects.filter(pk=run.pk).update(status='RUNNING')
        data = rows(bling.read('/caixas?' + urlencode(dict(pagina=run.page, dataInicial=run.start.isoformat(),
            dataFinal=run.end.isoformat(), idContaFinanceira=run.link.external.external_id,
            situacaoConciliacao=3, situacao=run.phase))))
        parsed = [parse_entry(row, run) for row in data]
        if len(set(ext for ext, _ in parsed)) != len(parsed):
            raise ValidationError('O Bling repetiu movimentos na página. Reconsulte o período.')
        with transaction.atomic():
            locked = BlingBankRun.objects.select_for_update().get(pk=run.pk)
            if locked.page != run.page or locked.phase != run.phase or locked.status not in ACTIVE:
                return
            for ext, values in parsed:
                prior = run.staged.filter(external_id=ext).first()
                if prior and prior.data['deleted'] == values['deleted']:
                    raise ValidationError('O Bling repetiu uma página. Reconsulte o período.')
                BlingBankStaging.objects.update_or_create(run=run, external_id=ext, defaults={'data': values})
            if parsed:
                if run.page >= 10000: raise ValidationError('Limite de páginas atingido. Reduza o período.')
                locked.page += 1
            elif run.phase == 'R':
                locked.phase, locked.page = 'E', 1
            else:
                publish(locked)
                return
            locked.attempts = 0
            locked.message = f'Atualizando extrato: página {locked.page} ({"movimentos" if locked.phase == "R" else "excluídos"}).'
            locked.next_attempt = timezone.now() + timedelta(seconds=1)
            locked.save()
    except PermissionDenied:
        BlingBankRun.objects.filter(pk=run.pk).update(status='FAILED', finished_at=timezone.now(),
            message='Consulta interrompida: usuário sem permissão financeira/Bling. Histórico salvo preservado.')
    except ValidationError as exc:
        attempts = run.attempts + 1
        BlingBankRun.objects.filter(pk=run.pk).update(attempts=attempts,
            status='FAILED' if attempts >= 3 else 'QUEUED',
            next_attempt=timezone.now()+timedelta(minutes=5),
            message=('; '.join(exc.messages) + (' Nova tentativa em 5 minutos.' if attempts < 3 else ' Use Atualizar para tentar novamente.'))[:500])


@transaction.atomic
def publish(run):
    # Publish only after both full paginations. A failed/partial fetch cannot erase the saved statement.
    link = BlingBankLink.objects.select_for_update().get(pk=run.link_id)
    now = timezone.now()
    BlingBankEntry.objects.filter(link=link, date__range=(run.start,run.end)).update(present=False)
    for row in run.staged.iterator():
        BlingBankEntry.objects.update_or_create(link=link, external_id=row.external_id,
            defaults=dict(row.data, present=True, checked_at=now))
    for offset in range((run.end-run.start).days+1):
        BlingBankDay.objects.update_or_create(link=link, date=run.start+timedelta(days=offset), defaults={'checked_at':now})
    run.status, run.finished_at, run.message = 'DONE', now, 'Extrato atualizado e salvo.'
    run.save()
    run.staged.all().delete()  # Transient page buffer only; published history is retained.
    audit(run.actor, run, 'bling_bank_imported', after={'start':str(run.start),'end':str(run.end)})
    if link.requested_through:
        if run.end < link.requested_through and link.automatic:
            enqueue(actor=run.actor, link_id=link.pk, automatic=True)
        else:
            link.requested_through = None
            link.save(update_fields=['requested_through'])


def comparison(link, start, end):
    """Net flows, not one-to-one transaction matching. Unknown coverage is never zero."""
    end = min(end, timezone.localdate())
    start = max(start, link.account.opening_date)
    if start > end: return None
    local = FinancialEntry.objects.filter(account=link.account, operation__status='POSTED', operation__date__lte=end)
    external = link.entries.filter(present=True, deleted=False)
    covered = set(link.days.filter(date__range=(min(start,link.start_date),end)).values_list('date',flat=True))
    local_daily = {r['operation__date']:r['net'] for r in local.filter(operation__date__gte=start).values('operation__date').annotate(net=Sum('amount'))}
    remote_daily = {r['date']:r['net'] for r in external.filter(date__range=(start,end)).values('date').annotate(net=Sum('amount'))}
    days = [start+timedelta(days=i) for i in range((end-start).days+1)]
    period_complete = all(day in covered for day in days)
    local_net = sum(local_daily.values(),ZERO)
    remote_net = sum(remote_daily.values(),ZERO) if period_complete else None
    balance_complete = end >= link.start_date and all(link.start_date+timedelta(days=i) in covered for i in range((end-link.start_date).days+1))
    remote_balance = None
    if balance_complete and link.opening_balance is not None:
        remote_balance = link.opening_balance + (external.filter(date__range=(link.start_date,end)).aggregate(v=Sum('amount'))['v'] or ZERO)
    local_balance = link.account.opening_balance + (local.aggregate(v=Sum('amount'))['v'] or ZERO)
    return dict(start=start,end=end,local_balance=local_balance,remote_balance=remote_balance,
        balance_difference=local_balance-remote_balance if remote_balance is not None else None,
        local_net=local_net,remote_net=remote_net,net_difference=local_net-remote_net if remote_net is not None else None,
        complete=period_complete, daily=[dict(date=d, local=local_daily.get(d,ZERO),
            remote=remote_daily.get(d,ZERO) if d in covered else None,
            difference=local_daily.get(d,ZERO)-remote_daily.get(d,ZERO) if d in covered else None) for d in reversed(days)])
