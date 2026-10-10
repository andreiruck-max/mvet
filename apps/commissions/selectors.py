from calendar import monthrange
from decimal import Decimal
from django.db.models import Q, Prefetch
from .models import CommissionPlan, Payee, Entry, Payment, Allocation
from .services import access, total, ZERO

def payees(actor):
    access(actor)
    return Payee.objects.all() if actor.has_perm('core.manage_commissions') else Payee.objects.filter(user=actor)

def plans(actor):
    return CommissionPlan.objects.filter(payee__in=payees(actor)).select_related('sale','payee').prefetch_related(
        'sale__items','installments__entries__allocations__payment','installments__entries__command').order_by('sale__date','sale__invoice_number','pk')

def decorate(plan):
    parts=list(plan.installments.all());plan.parts=parts
    plan.released=ZERO;plan.paid=ZERO;plan.received=ZERO;plan.face=ZERO;plan.received_count=0
    for part in parts:
        events=list(part.entries.all())
        part.received=sum((e.received for e in events),ZERO)
        part.released=sum((e.released for e in events),ZERO)
        part.paid=sum((a.amount for e in events for a in e.allocations.all()),ZERO)
        part.pending=part.released-part.paid;part.remaining=part.amount-part.received
        part.last_received=max((e.date for e in events if e.received>0),default=None)
        part.state='Cancelada' if plan.cancelled else 'Recebida' if part.received==part.amount else 'Parcialmente recebida' if part.received else 'Estornada' if any(e.received<0 for e in events) else 'Em aberto'
        plan.released+=part.released;plan.paid+=part.paid;plan.received+=part.received;plan.face+=part.amount
        plan.received_count+=int(part.received==part.amount)
    plan.last_received=max((i.last_received for i in parts if i.last_received),default=None)
    plan.pending=plan.released-plan.paid
    plan.receipt_state='FULL' if plan.received==plan.face else 'PARTIAL' if plan.received else 'OPEN'
    plan.state='CANCELLED' if plan.cancelled else 'NEGATIVE' if plan.pending<0 else 'PAID' if plan.paid and plan.paid>=plan.total else 'PART_PAID' if plan.paid else 'RELEASED' if plan.released==plan.total and plan.total else 'PARTIAL' if plan.released else 'FORECAST'
    plan.state_label=dict([('CANCELLED','Cancelada'),('NEGATIVE','A compensar'),('PAID','Totalmente paga'),('PART_PAID','Parcialmente paga'),('RELEASED','Totalmente liberada'),('PARTIAL','Parcialmente liberada'),('FORECAST','Prevista')])[plan.state]
    plan.face_difference=plan.sale.products_amount-plan.sale.discount+plan.sale.shipping_received-plan.face
    return plan

def filtered(actor,d):
    rows=plans(actor)
    if d.get('payee'):rows=rows.filter(payee=d['payee'])
    if d.get('q'):
        q=d['q'];condition=Q(customer__icontains=q)|Q(sale__invoice_number__icontains=q)
        if q.isdecimal() and len(q)<=18:condition|=Q(sale_id=int(q))
        rows=rows.filter(condition)
    for key,field in [('start','sale__date__gte'),('end','sale__date__lte')]:
        if d.get(key):rows=rows.filter(**{field:d[key]})
    receipt=Entry.objects.filter(received__gt=0)
    if d.get('received_start'):receipt=receipt.filter(date__gte=d['received_start'])
    if d.get('received_end'):receipt=receipt.filter(date__lte=d['received_end'])
    if d.get('received_start') or d.get('received_end'):rows=rows.filter(installments__entries__in=receipt).distinct()
    result=[]
    for plan in rows:
        decorate(plan)
        if d.get('state') and plan.state!=d['state']:continue
        if d.get('receipt') and plan.receipt_state!=d['receipt']:continue
        if d.get('payment')=='PENDING' and plan.pending<=0:continue
        if d.get('payment')=='PAID' and not(plan.paid>0 and plan.pending<=0):continue
        if d.get('payment')=='UNPAID' and plan.paid!=0:continue
        result.append(plan)
    return result

def monthly(actor,month,payee=None):
    start=month.replace(day=1);end=start.replace(day=monthrange(start.year,start.month)[1])
    people=payees(actor)
    if payee:people=people.filter(pk=payee.pk)
    events=Entry.objects.filter(installment__plan__payee__in=people,date__lte=end).select_related(
        'installment__plan__sale','installment__plan__payee','command').prefetch_related('allocations__payment').order_by('date','pk')
    payments=Payment.objects.filter(payee__in=people,date__range=(start,end))
    payment_sums={p.pk:total(payments.filter(payee=p),'amount') for p in people}
    report={p.pk:{'payee':p,'released':ZERO,'paid':payment_sums[p.pk],'month_allocated':ZERO,'previous':ZERO,'pending':ZERO,'total':ZERO} for p in people}
    detail=[]
    for event in events:
        r=report[event.installment.plan.payee_id]
        event.paid=sum((a.amount for a in event.allocations.all() if a.payment.date<=end),ZERO)
        event.pending=event.released-event.paid
        if event.date>=start:
            r['released']+=event.released;r['month_allocated']+=event.paid;r['pending']+=event.pending
        else:r['previous']+=event.pending
        if event.date>=start or event.pending:detail.append(event)
    for r in report.values():r['total']=r['previous']+r['pending']
    return list(report.values()),detail,start,end
