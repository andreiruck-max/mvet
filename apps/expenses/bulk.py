"""One idempotent settlement per expense, inside one atomic batch."""
from decimal import Decimal
from uuid import UUID, uuid5
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.core.services import require
from apps.inventory.services import domain_lock
from apps.finance.services import settle
from apps.finance.models import FinancialAccount
from .models import Expense


def check_access(actor):
    for permission in ['core.operate_expenses','core.operate_finance','core.pay_titles']:require(actor,permission)


def selection(ids):
    if not ids or len(ids)>100 or len(set(ids))!=len(ids):raise ValidationError('Selecione de 1 a 100 despesas distintas.')
    rows=list(Expense.objects.filter(pk__in=ids).select_related('title').order_by('pk'))
    if len(rows)!=len(ids):raise ValidationError('Uma das despesas selecionadas não existe.')
    for obj in rows:
        if obj.status!='ACTIVE' or not obj.title_id or obj.title.status!='OPEN' or obj.title.remaining<=0:
            raise ValidationError(f'Despesa {obj.pk}: selecione somente despesas com saldo pendente.')
    return rows


def preview_rows(rows):
    return [dict(id=obj.pk,revision=obj.revision,title_id=obj.title_id,title_revision=obj.title.revision,
                 principal=str(obj.title.remaining)) for obj in rows]


@transaction.atomic
def settle_batch(*,actor,key,rows,account_id,date):
    check_access(actor);domain_lock()
    try:key=UUID(str(key))
    except (TypeError,ValueError):raise ValidationError('Identificador do lote inválido.')
    if not FinancialAccount.objects.filter(pk=account_id).exists():raise ValidationError('Conta não encontrada. Confira o lote novamente.')
    ids=[r['id'] for r in rows]
    if not ids or len(ids)>100 or len(set(ids))!=len(ids):raise ValidationError('Lote inválido.')
    objects={obj.pk:obj for obj in Expense.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
    if len(objects)!=len(ids):raise ValidationError('Uma das despesas não existe mais. Confira novamente.')
    operations=[]
    for row in sorted(rows,key=lambda r:r['id']):
        obj=objects[row['id']]
        if obj.status!='ACTIVE' or obj.revision!=row['revision'] or obj.title_id!=row['title_id']:
            raise ValidationError('Uma despesa mudou após a conferência. Selecione novamente.')
        operations.append(settle(actor=actor,key=uuid5(key,f'expense:{obj.pk}'),title_id=obj.title_id,
            account_id=account_id,date=date,principal=Decimal(row['principal']),interest=Decimal(0),
            discount=Decimal(0),actual=Decimal(row['principal']),revision=row['title_revision']))
    return operations
