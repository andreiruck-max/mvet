"""Explicit, audited automatic settlement. Never initiates a bank payment."""
from uuid import uuid4
from decimal import Decimal
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from apps.core.services import require, audit
from apps.inventory.services import domain_lock
from .models import FinancialTitle, DuePayment
from .services import settle, account_for


@transaction.atomic
def configure(*, actor, title_id, account_id, enabled, revision):
    require(actor, 'core.operate_finance'); require(actor, 'core.pay_titles'); domain_lock()
    title=FinancialTitle.objects.select_for_update().get(pk=title_id)
    if title.direction!='PAY' or title.status!='OPEN' or not title.remaining:
        raise ValidationError('Somente títulos a pagar com saldo podem ser programados.')
    if title.revision!=revision:raise ValidationError('Título alterado. Reabra antes de programar.')
    if enabled:
        if title.due_date < timezone.localdate():raise ValidationError('Vencimento já passou. Use a baixa manual.')
        account=account_for(account_id,title.due_date)
    else:
        account=None
    obj, _=DuePayment.objects.get_or_create(title=title,defaults={'actor':actor,'account':account})
    obj.enabled=enabled;obj.actor=actor;obj.account=account;obj.message='';obj.save()
    title.revision+=1;title.save(update_fields=['revision'])
    audit(actor,obj,'schedule_due_payment',after={'enabled':enabled,'account':account_id,'due_date':str(title.due_date)})
    return obj


@transaction.atomic
def execute(pk):
    domain_lock()
    obj=DuePayment.objects.select_for_update(of=('self',)).select_related('title','account','actor').get(pk=pk)
    title=FinancialTitle.objects.select_for_update().get(pk=obj.title_id)
    if not obj.enabled or title.due_date>timezone.localdate():return
    if title.status!='OPEN' or not title.remaining:
        obj.enabled=False;obj.message='Encerrado: título cancelado ou já liquidado.';obj.save();return
    if not obj.actor.is_active:raise PermissionDenied
    # Reuse the existing locked, permission-checked and audited settlement service.
    op=settle(actor=obj.actor,key=uuid4(),title_id=title.pk,account_id=obj.account_id,
        date=title.due_date,principal=title.remaining,interest=Decimal(0),discount=Decimal(0),actual=title.remaining,
        notes='Baixa automática no vencimento autorizada no MVet.',revision=title.revision)
    obj.enabled=False;obj.operation=op;obj.message='Baixa no vencimento concluída.';obj.save()
    audit(obj.actor,obj,'execute_due_payment',after={'operation':op.pk})


def tick():
    # Bounded batch. Domain mutex serializes with manual payments and cancellation.
    for pk in DuePayment.objects.filter(enabled=True,title__due_date__lte=timezone.localdate()).order_by('title__due_date','pk').values_list('pk',flat=True)[:50]:
        try:execute(pk)
        except (ValidationError, PermissionDenied) as exc:
            message='Permissão para baixa automática indisponível.' if isinstance(exc,PermissionDenied) else '; '.join(exc.messages)
            DuePayment.objects.filter(pk=pk,enabled=True).update(enabled=False,message=message[:500])
