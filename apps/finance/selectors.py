from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from django.db.models import F, Q, Sum
from django.utils import timezone
from .models import FinancialAccount as Account, FinancialTitle as Title, FinancialEntry as Entry

ZERO=Decimal('0.00')


def titles(data):
    rows=Title.objects.select_related('account','purchase_installment__purchase','sale')
    if data.get('q'):
        rows=rows.filter(Q(description__icontains=data['q'])|Q(counterparty__icontains=data['q']))
    for field in ['direction','account','category']:
        if data.get(field): rows=rows.filter(**{field:data[field]})
    if data.get('start'): rows=rows.filter(due_date__gte=data['start'])
    if data.get('end'): rows=rows.filter(due_date__lte=data['end'])
    status=data.get('status','pending')
    if status=='cancelled': rows=rows.filter(status='CANCELLED')
    elif status in ['pending','overdue','paid']:
        rows=rows.filter(status='OPEN')
        rows=rows.filter(settled=F('amount')) if status=='paid' else rows.filter(settled__lt=F('amount'))
        if status=='overdue': rows=rows.filter(due_date__lt=timezone.localdate())
    return rows.order_by(data.get('sort') or 'due_date','pk')


def daily_cash(start,end,account_id=None):
    """Bounded report. Actual ledger is immutable; balances are derived, never cached."""
    today=timezone.localdate()
    accounts=Account.objects.filter(opening_date__lte=end)
    if account_id: accounts=accounts.filter(pk=account_id)
    accounts=list(accounts)
    ids=[a.pk for a in accounts]
    posted=Entry.objects.filter(account_id__in=ids,operation__status='POSTED',operation__date__lte=min(end,today))
    prior={r['account_id']:r['total'] for r in posted.filter(operation__date__lt=start).values('account_id').annotate(total=Sum('amount'))}
    movements=defaultdict(lambda:[ZERO,ZERO])
    for row in posted.filter(operation__date__gte=start).values('account_id','operation__date').annotate(credit=Sum('amount',filter=Q(amount__gt=0)),debit=Sum('amount',filter=Q(amount__lt=0))):
        movements[(row['account_id'],row['operation__date'])]=[row['credit'] or ZERO,-(row['debit'] or ZERO)]
    forecast=defaultdict(lambda:ZERO)
    opening_dates={a.pk:a.opening_date for a in accounts}
    # Overdue forecasts roll forward to today; history is only actual cash.
    for row in Entry.objects.filter(account_id__in=ids,operation__status='PLANNED',operation__date__lte=end).values('account_id','operation__date').annotate(total=Sum('amount')):
        date=max(row['operation__date'],today)
        if date<=end: forecast[(row['account_id'],date)]+=row['total']
    pending=Title.objects.filter(status='OPEN',settled__lt=F('amount'),due_date__lte=end)
    for row in pending.filter(account_id__in=ids).values('account_id','due_date').annotate(total=Sum(F('amount')-F('settled'),filter=Q(direction='RECEIVE')),pay=Sum(F('amount')-F('settled'),filter=Q(direction='PAY'))):
        date=max(row['due_date'],today,opening_dates[row['account_id']])
        if date<=end: forecast[(row['account_id'],date)]+=(row['total'] or ZERO)-(row['pay'] or ZERO)
    unallocated=pending.filter(account__isnull=True).aggregate(pay=Sum(F('amount')-F('settled'),filter=Q(direction='PAY')),receive=Sum(F('amount')-F('settled'),filter=Q(direction='RECEIVE')))
    result=[]
    for account in accounts:
        balance=account.opening_balance+prior.get(account.pk,ZERO) if account.opening_date<=start else ZERO
        projected=balance+sum((v for (a,d),v in forecast.items() if a==account.pk and d<start),ZERO)
        date=start
        while date<=end:
            if date<account.opening_date:
                date+=timedelta(days=1); continue
            if date==account.opening_date and date>start: balance=projected=account.opening_balance
            credit,debit=movements[(account.pk,date)]
            begin=balance; balance+=credit-debit
            projected+=credit-debit+forecast[(account.pk,date)]
            result.append(dict(account=account,date=date,initial=begin,credits=credit,debits=debit,final=balance,projected=projected,forecast=forecast[(account.pk,date)]))
            date+=timedelta(days=1)
    return result, {k:v or ZERO for k,v in unallocated.items()}
