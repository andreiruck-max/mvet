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


def daily_cash(start,end,account_id=None, *, active_only=False):
    """Bounded report. Actual ledger is immutable; balances are derived, never cached."""
    today=timezone.localdate()
    accounts=Account.objects.filter(opening_date__lte=end)
    if active_only: accounts=accounts.filter(active=True)
    if account_id: accounts=accounts.filter(pk=account_id)
    accounts=list(accounts)
    ids=[a.pk for a in accounts]
    posted=Entry.objects.filter(account_id__in=ids,operation__status='POSTED',operation__date__lte=min(end,today))
    prior={r['account_id']:r['total'] for r in posted.filter(operation__date__lt=start).values('account_id').annotate(total=Sum('amount'))}
    movements=defaultdict(lambda:[ZERO,ZERO])
    for row in posted.filter(operation__date__gte=start).values('account_id','operation__date').annotate(credit=Sum('amount',filter=Q(amount__gt=0)),debit=Sum('amount',filter=Q(amount__lt=0))):
        movements[(row['account_id'],row['operation__date'])]=[row['credit'] or ZERO,-(row['debit'] or ZERO)]
    forecast=defaultdict(lambda:ZERO)
    forecast_credits=defaultdict(lambda:ZERO)
    forecast_debits=defaultdict(lambda:ZERO)
    opening_dates={a.pk:a.opening_date for a in accounts}
    # Overdue forecasts roll forward to today; history is only actual cash.
    for row in Entry.objects.filter(account_id__in=ids,operation__date__lte=end).filter(Q(operation__status='PLANNED') | Q(operation__status='POSTED', operation__date__gt=today)).values('account_id','operation__date').annotate(total=Sum('amount'),credit=Sum('amount',filter=Q(amount__gt=0)),debit=Sum('amount',filter=Q(amount__lt=0))):
        date=max(row['operation__date'],today)
        if date<=end:
            forecast[(row['account_id'],date)]+=row['total']
            forecast_credits[(row['account_id'],date)]+=row['credit'] or ZERO
            forecast_debits[(row['account_id'],date)]-=row['debit'] or ZERO
    pending=Title.objects.filter(status='OPEN',settled__lt=F('amount'),due_date__lte=end)
    for row in pending.filter(account_id__in=ids).values('account_id','due_date').annotate(total=Sum(F('amount')-F('settled'),filter=Q(direction='RECEIVE')),pay=Sum(F('amount')-F('settled'),filter=Q(direction='PAY'))):
        date=max(row['due_date'],today,opening_dates[row['account_id']])
        if date<=end:
            forecast[(row['account_id'],date)]+=(row['total'] or ZERO)-(row['pay'] or ZERO)
            forecast_credits[(row['account_id'],date)]+=row['total'] or ZERO
            forecast_debits[(row['account_id'],date)]+=row['pay'] or ZERO
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
            result.append(dict(account=account,date=date,initial=begin,credits=credit,debits=debit,final=balance,projected=projected,projected_credits=credit+forecast_credits[(account.pk,date)],projected_debits=debit+forecast_debits[(account.pk,date)],forecast=forecast[(account.pk,date)]))
            date+=timedelta(days=1)
    return result, {k:v or ZERO for k,v in unallocated.items()}


def cash_summary(start, end, account_id=None, *, active_only=False):
    """Period endpoint, independent of pagination; company includes unassigned debts."""
    rows, unallocated = daily_cash(start, end, account_id, active_only=active_only)
    final_rows = [row for row in rows if row['date'] == end]
    actual = sum((row['final'] for row in final_rows), ZERO)
    projected = sum((row['projected'] for row in final_rows), ZERO)
    if not account_id and end >= timezone.localdate():
        projected += unallocated['receive'] - unallocated['pay']
    return {'actual': actual, 'projected': projected, 'unallocated': unallocated, 'end': end}


def cash_matrix(rows, dates, mode='projected'):
    # Transpose daily balances, leaving blanks before account opening.
    accounts = {}
    totals = {day: {'credits': ZERO, 'debits': ZERO, 'balance': ZERO} for day in dates}
    for row in rows:
        account = row['account']
        group = accounts.setdefault(account.pk, {'account': account, 'by_date': {}})
        cell = {'date': row['date'],
                'credits': row['credits'] if mode == 'actual' else row['projected_credits'],
                'debits': row['debits'] if mode == 'actual' else row['projected_debits'],
                'balance': row['final'] if mode == 'actual' else row['projected']}
        group['by_date'][row['date']] = cell
        for key in ('credits','debits','balance'):
            totals[row['date']][key] += cell[key]
    return ([{'account': group['account'], 'cells': [group['by_date'].get(day) for day in dates]}
             for group in accounts.values()], [totals[day] for day in dates])


def account_statement(account, start, end):
    from django.db.models import Case, When, Value, Window, DecimalField
    money=DecimalField(max_digits=24,decimal_places=2)
    prior=Entry.objects.filter(account=account,operation__status='POSTED',operation__date__lt=start,
        operation__date__lte=timezone.localdate()).aggregate(total=Sum('amount'))['total'] or ZERO
    initial=account.opening_balance+prior if account.opening_date<=start else ZERO
    rows=Entry.objects.filter(account=account,operation__date__range=(start,end)).select_related('operation','operation__title').order_by('operation__date','pk')
    # Opening can occur inside the selected range; every entry is on/after it.
    running_base=account.opening_balance+prior
    rows=rows.annotate(running_balance=Value(running_base,output_field=money)+Window(
        expression=Sum(Case(When(operation__status='POSTED',operation__date__lte=timezone.localdate(),then=F('amount')),default=Value(ZERO),output_field=money)),
        order_by=[F('operation__date').asc(),F('pk').asc()]))
    return rows, initial
