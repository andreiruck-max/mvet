"""Commission subledger. Receipt evidence and payments do not post bank entries."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4
from calendar import monthrange
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone
from apps.core.services import require, audit
from apps.inventory.services import domain_lock, number, _fingerprint
from apps.sales.models import Sale, SaleCorrection
from .models import Payee, CommissionSettings, CommissionPlan, Installment, Command, Entry, Payment, Allocation

ZERO = Decimal('0.00')
CENT = Decimal('.01')

def manage(actor): require(actor, 'core.manage_commissions')

def access(actor):
    if not actor.has_perm('core.manage_commissions'): require(actor, 'core.view_own_commissions')

def total(query, field): return query.aggregate(v=Sum(field))['v'] or ZERO
def rounded(value): return value.quantize(CENT, rounding=ROUND_HALF_UP)

def date_check(date, minimum=None):
    if not date or date > timezone.localdate() or (minimum and date < minimum):
        raise ValidationError('Informe a data efetiva, entre a origem do registro e hoje.')

def reason_check(reason):
    reason = reason.strip()
    if not reason or len(reason)>500: raise ValidationError('Informe um motivo / observação de até 500 caracteres.')
    return reason

def command(actor, key, kind, reason, payload, before=None, after=None):
    reason=reason_check(reason); key=UUID(str(key))
    fingerprint=_fingerprint([actor.pk,kind,reason,payload])
    previous=Command.objects.filter(key=key).first()
    if previous:
        if previous.fingerprint!=fingerprint: raise ValidationError('Envio já utilizado com outros dados.')
        return previous, False
    return Command.objects.create(key=key, fingerprint=fingerprint, actor=actor, kind=kind,
        reason=reason, before=before or {}, after=after or {}), True

def weights(amount, installments):
    """Cumulative rounding conserves the total, including small equal installments."""
    denominator=sum((i.amount for i in installments),ZERO)
    cumulative=ZERO; allocated=ZERO
    for i in installments:
        cumulative+=i.amount
        target=rounded(amount*cumulative/denominator)
        i.forecast=target-allocated;allocated=target
        i.save(update_fields=['forecast'])

def snapshot(plan):
    return {'plan_id':plan.pk,'sale_id':plan.sale_id,'payee_id':plan.payee_id,'base':str(plan.base),
        'rate':str(plan.rate),'rate_source':plan.rate_source,'total':str(plan.total),
        'override_total':str(plan.override_total) if plan.override_total is not None else None,
        'cancelled':plan.cancelled,'revision':plan.revision}

def write_sale_cost(sale, actor, amount, reason):
    """Same audited exception to immutable sales used by the existing correction flow."""
    if sale.commission == amount: return
    from apps.sales.corrections import snapshot as sale_snapshot
    before=sale_snapshot(sale);sale.commission=amount;after=sale_snapshot(sale)
    correction=SaleCorrection.objects.create(sale=sale,actor=actor,reason=reason,before_revision=sale.revision,before=before,after=after)
    if connection.vendor=='postgresql':
        with connection.cursor() as cur:cur.execute("SELECT set_config('mvet.sale_correction', %s, true)",[str(correction.key)])
    try:
        sale.revision+=1;sale.save(update_fields=['commission','revision'])
    finally:
        if connection.vendor=='postgresql':
            with connection.cursor() as cur:cur.execute("SELECT set_config('mvet.sale_correction', '', true)")
    audit(actor,sale,'commission_cost',before,dict(after,reason=reason))

@transaction.atomic
def configure(*,actor,data,pk=None):
    manage(actor);domain_lock()
    obj=Payee.objects.select_for_update().get(pk=pk) if pk else Payee()
    before={f:str(getattr(obj,f)) for f in ('name','kind','user_id','default_rate','active')}
    for field in ('name','kind','user','default_rate','active'): setattr(obj,field,data[field])
    # Changing a linked login would expose someone else's historical commissions.
    if pk and before['user_id'] not in ('None',str(obj.user_id)) and obj.plans.exists():
        raise ValidationError('Comissionado com histórico: preserve o usuário vinculado; cadastre outra pessoa.')
    obj.full_clean();obj.save();audit(actor,obj,'commission_payee',before,{f:str(getattr(obj,f)) for f in before})
    return obj

@transaction.atomic
def configure_default(*,actor,rate,reason):
    manage(actor);domain_lock();reason=reason_check(reason)
    obj,_=CommissionSettings.objects.get_or_create(pk=1)
    before=str(obj.default_rate);obj.default_rate=rate;obj.full_clean();obj.save()
    audit(actor,obj,'commission_default',{'rate':before},{'rate':str(rate),'reason':reason})

@transaction.atomic
def create_plan(*,actor,sale_id,payee_id,customer,rate,installments,key,reason):
    manage(actor);domain_lock()
    sale=Sale.objects.select_for_update().get(pk=sale_id)
    rows=[(date,number(amount,CENT)) for date,amount in installments]
    payload=[sale_id,payee_id,customer,str(rate),[(str(d),str(a)) for d,a in rows]]
    cmd,fresh=command(actor,key,'CREATE',reason,payload)
    if not fresh:return CommissionPlan.objects.get(sale=sale)
    if sale.status!='CONFIRMED' or CommissionPlan.objects.filter(sale=sale).exists():
        raise ValidationError('Selecione uma venda confirmada ainda sem controle de comissão.')
    payee=Payee.objects.get(pk=payee_id)
    if not payee.active:raise ValidationError('Selecione um comissionado ativo.')
    if not 1<=len(rows)<=60 or any(d<sale.date for d,a in rows):raise ValidationError('Informe de 1 a 60 parcelas, com vencimentos a partir da venda.')
    face=sale.products_amount-sale.discount+sale.shipping_received
    if sum((a for d,a in rows),ZERO)!=face:raise ValidationError(f'As parcelas devem somar produtos − desconto + frete: R$ {face:.2f}. Ajuste a diferença antes de salvar.')
    default=CommissionSettings.objects.filter(pk=1).first()
    if rate is None and payee.default_rate is None and default is None:
        raise ValidationError('Informe um percentual na venda ou configure o percentual do comissionado / padrão global.')
    source='MANUAL' if rate is not None else 'PAYEE' if payee.default_rate is not None else 'DEFAULT'
    selected=rate if rate is not None else payee.default_rate if payee.default_rate is not None else default.default_rate
    plan=CommissionPlan(sale=sale,payee=payee,customer=customer.strip(),rate=selected,rate_source=source,
        base=sale.products_amount-sale.discount,total=rounded((sale.products_amount-sale.discount)*selected/100))
    plan.full_clean();plan.save()
    parts=[Installment.objects.create(plan=plan,number=n,due_date=d,amount=a) for n,(d,a) in enumerate(rows,1)]
    weights(plan.total,parts)
    write_sale_cost(sale,actor,plan.total,reason)
    audit(actor,plan,'commission_create',{},dict(snapshot(plan),command_id=cmd.pk))
    return plan

def rebalance(plan,cmd,date):
    for item in plan.installments.all():
        received=total(item.entries,'received');current=total(item.entries,'released')
        target=ZERO if plan.cancelled else rounded(item.forecast*received/item.amount)
        if target!=current:Entry.objects.create(installment=item,command=cmd,date=date,released=target-current)

@transaction.atomic
def revise_schedule(*,actor,plan_id,revision,rows,key,reason):
    manage(actor);domain_lock();plan=CommissionPlan.objects.select_for_update().select_related('sale').get(pk=plan_id)
    items=list(plan.installments.all())
    before={'schedule':[{'id':i.pk,'amount':str(i.amount),'due_date':str(i.due_date)} for i in items]}
    payload=[plan_id,revision,[(r['installment_id'],str(r['due_date']),str(r['amount'])) for r in rows]]
    cmd,fresh=command(actor,key,'SCHEDULE',reason,payload,before=before)
    if not fresh:return plan
    if plan.cancelled or plan.revision!=revision:raise ValidationError('Registro alterado ou cancelado. Reabra a página.')
    if len(rows)!=len(items) or {r['installment_id'] for r in rows}!={i.pk for i in items}:
        raise ValidationError('Preserve as parcelas existentes; histórico não pode ser removido.')
    data={r['installment_id']:r for r in rows}
    for i in items:
        r=data[i.pk];amount=number(r['amount'],CENT)
        if amount<total(i.entries,'received'):raise ValidationError(f'Parcela {i.number}: valor menor que o já recebido. Estorne o recebimento incorreto antes de ajustar.')
        if r['due_date']<plan.sale.date:raise ValidationError('Vencimento anterior à venda.')
        i.amount=amount;i.due_date=r['due_date']
    face=plan.sale.products_amount-plan.sale.discount+plan.sale.shipping_received
    if sum((i.amount for i in items),ZERO)!=face:raise ValidationError(f'As parcelas devem somar R$ {face:.2f}.')
    for i in items:i.save(update_fields=['amount','due_date'])
    weights(plan.total,items);rebalance(plan,cmd,timezone.localdate())
    plan.revision+=1;plan.save(update_fields=['revision'])
    audit(actor,plan,'commission_schedule',before,{'schedule':[{'id':i.pk,'amount':str(i.amount),'due_date':str(i.due_date)} for i in items],'reason':reason})
    return plan

@transaction.atomic
def adjust(*,actor,plan_id,revision,rate,override_total,key,reason):
    manage(actor);domain_lock();plan=CommissionPlan.objects.select_for_update().select_related('sale').get(pk=plan_id)
    before=snapshot(plan)
    cmd,fresh=command(actor,key,'ADJUST',reason,[plan_id,revision,str(rate),str(override_total)],before=before)
    if not fresh:return plan
    if plan.cancelled or plan.revision!=revision:raise ValidationError('Registro alterado ou cancelado. Reabra a página.')
    plan.rate=rate;plan.rate_source='MANUAL';plan.override_total=override_total
    plan.total=number(override_total,CENT,zero=True) if override_total is not None else rounded(plan.base*rate/100)
    plan.full_clean();plan.revision+=1;plan.save()
    weights(plan.total,list(plan.installments.all()));rebalance(plan,cmd,timezone.localdate())
    write_sale_cost(plan.sale,actor,plan.total,reason)
    audit(actor,plan,'commission_adjust',before,dict(snapshot(plan),reason=reason,command_id=cmd.pk))
    return plan

@transaction.atomic
def receive(*,actor,installment_id,amount,date,key,reason):
    manage(actor);domain_lock();item=Installment.objects.select_for_update().select_related('plan__sale').get(pk=installment_id)
    amount=number(amount,CENT);date_check(date,item.plan.sale.date)
    cmd,fresh=command(actor,key,'RECEIVE',reason,[installment_id,str(amount),str(date)])
    if not fresh:return cmd.entries.get()
    if item.plan.cancelled:raise ValidationError('Venda cancelada: não é possível registrar recebimento.')
    received=total(item.entries,'received')
    if received+amount>item.amount:raise ValidationError(f'Recebimento excede o saldo da parcela: R$ {item.amount-received:.2f}.')
    # A correction is booked today; don't allow later edits to invent an earlier entitlement.
    latest=item.entries.order_by('-date','-pk').first()
    if latest and date<latest.date:raise ValidationError('Data anterior ao último evento da parcela. Use a data atual com justificativa.')
    delta=rounded(item.forecast*(received+amount)/item.amount)-total(item.entries,'released')
    event=Entry.objects.create(installment=item,command=cmd,date=date,received=amount,released=delta)
    item.plan.revision+=1;item.plan.save(update_fields=['revision'])
    audit(actor,item.plan,'commission_receipt',{}, {'entry_id':event.pk,'received':str(amount),'released':str(delta),'reason':reason})
    return event

@transaction.atomic
def reverse_receipt(*,actor,entry_id,date,key,reason):
    manage(actor);domain_lock();original=Entry.objects.select_related('installment__plan').get(pk=entry_id)
    date_check(date,original.date)
    cmd,fresh=command(actor,key,'REVERSE_RECEIPT',reason,[entry_id,str(date)])
    if not fresh:return cmd.entries.get()
    if original.received<=0 or Entry.objects.filter(reversal_of=original).exists():raise ValidationError('Recebimento inválido ou já estornado.')
    item=original.installment;plan=item.plan
    latest=item.entries.order_by('-date','-pk').first()
    if latest and date<latest.date:raise ValidationError('Estorno deve ocorrer a partir do último evento da parcela.')
    received=total(item.entries,'received')-original.received
    target=ZERO if plan.cancelled else rounded(item.forecast*received/item.amount)
    event=Entry.objects.create(installment=item,command=cmd,date=date,received=-original.received,
        released=target-total(item.entries,'released'),reversal_of=original)
    plan.revision+=1;plan.save(update_fields=['revision'])
    audit(actor,plan,'commission_receipt_reversal',{}, {'entry_id':event.pk,'reason':reason})
    return event

def balance(payee,through=None):
    entries=Entry.objects.filter(installment__plan__payee=payee);payments=Payment.objects.filter(payee=payee)
    if through:entries=entries.filter(date__lte=through);payments=payments.filter(date__lte=through)
    return total(entries,'released')-total(payments,'amount')

def available_credits(payee,through=None):
    """Apply negative events to their own installment before allocating a payout.

    A zero-net cancelled installment must never absorb a payment owed by another
    sale. Targeted reversals consume their original credit first; remaining
    adjustments consume oldest unpaid credits within the same installment.
    """
    events=Entry.objects.filter(installment__plan__payee=payee).prefetch_related('allocations').order_by('date','pk')
    if through:events=events.filter(date__lte=through)
    groups={}
    for event in events:groups.setdefault(event.installment_id,[]).append(event)
    result={}
    for group in groups.values():
        credits={e.pk:max(ZERO,e.released-sum((a.amount for a in e.allocations.all()),ZERO)) for e in group if e.released>0}
        for event in group:
            if event.released>=0:continue
            debt=-event.released
            order=list(credits)
            if event.reversal_of_id in credits:order=[event.reversal_of_id]+[pk for pk in order if pk!=event.reversal_of_id]
            for pk in order:
                consume=min(debt,credits[pk]);credits[pk]-=consume;debt-=consume
                if not debt:break
        result.update(credits)
    return result

@transaction.atomic
def pay(*,actor,payee_id,amount,date,period,method,key,reason):
    manage(actor);domain_lock();payee=Payee.objects.select_for_update().get(pk=payee_id)
    amount=number(amount,CENT);date_check(date);period=period.replace(day=1)
    end=period.replace(day=monthrange(period.year,period.month)[1]);cutoff=min(date,end)
    cmd,fresh=command(actor,key,'PAY',reason,[payee_id,str(amount),str(date),str(period),method])
    if not fresh:return cmd.payment
    if not method.strip() or len(method)>100:raise ValidationError('Informe a forma de pagamento.')
    # Never let backdated payouts ignore newer payments or known clawbacks.
    available=min(balance(payee),balance(payee,cutoff))
    if amount>available:raise ValidationError(f'Pagamento excede saldo disponível (já descontadas compensações): R$ {available:.2f}.')
    entries=Entry.objects.filter(installment__plan__payee=payee,released__gt=0,date__lte=cutoff).order_by('date','pk')
    current_credits=available_credits(payee);period_credits=available_credits(payee,cutoff)
    allocations=[];remaining=amount
    for entry in entries:
        outstanding=min(current_credits.get(entry.pk,ZERO),period_credits.get(entry.pk,ZERO))
        take=min(remaining,max(ZERO,outstanding))
        if take:allocations.append((entry,take));remaining-=take
        if not remaining:break
    if remaining:raise ValidationError('Saldo do período já alocado a pagamentos posteriores. Confira o histórico.')
    payment=Payment.objects.create(payee=payee,command=cmd,date=date,period=period,amount=amount,method=method.strip())
    for entry,value in allocations:Allocation.objects.create(payment=payment,entry=entry,amount=value)
    audit(actor,payment,'commission_payment',{}, {'amount':str(amount),'payee_id':payee.pk,'reason':reason})
    return payment

@transaction.atomic
def reverse_payment(*,actor,payment_id,date,key,reason):
    manage(actor);domain_lock();original=Payment.objects.get(pk=payment_id);date_check(date,original.date)
    cmd,fresh=command(actor,key,'REVERSE_PAYMENT',reason,[payment_id,str(date)])
    if not fresh:return cmd.payment
    if original.amount<=0 or Payment.objects.filter(reversal_of=original).exists():raise ValidationError('Pagamento inválido ou já estornado.')
    payment=Payment.objects.create(payee=original.payee,command=cmd,date=date,period=original.period,
        amount=-original.amount,method=original.method,reversal_of=original)
    for alloc in original.allocations.all():Allocation.objects.create(payment=payment,entry=alloc.entry,amount=-alloc.amount)
    audit(actor,payment,'commission_payment_reversal',{}, {'original':original.pk,'reason':reason})
    return payment

def sale_state_changed(sale,actor,reason):
    """Internal hook: the caller already holds the atomic sale/domain lock."""
    plan=CommissionPlan.objects.filter(sale=sale).first()
    if not plan:return
    before=snapshot(plan);plan.cancelled=sale.status=='CANCELLED';plan.revision+=1;plan.save()
    cmd,_=command(actor,uuid4(),'SALE_STATE',reason,[sale.pk,sale.revision],before=before,after=snapshot(plan))
    rebalance(plan,cmd,timezone.localdate())
    audit(actor,plan,'commission_sale_state',before,snapshot(plan))

def sync_sale_values(sale,actor,reason):
    plan=CommissionPlan.objects.get(sale=sale)
    base=sale.products_amount-sale.discount
    if base!=plan.base:
        before=snapshot(plan);plan.base=base
        plan.total=plan.override_total if plan.override_total is not None else rounded(base*plan.rate/100)
        plan.revision+=1;plan.full_clean();plan.save()
        cmd,_=command(actor,uuid4(),'SALE_VALUES',reason,[sale.pk,sale.revision,str(base)],before=before,after=snapshot(plan))
        weights(plan.total,list(plan.installments.all()));rebalance(plan,cmd,timezone.localdate())
        audit(actor,plan,'commission_sale_values',before,snapshot(plan))
    sale.commission=plan.total
