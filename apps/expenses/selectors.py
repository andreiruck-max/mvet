import calendar
from datetime import timedelta
from decimal import Decimal
from django.db.models import Q, F, Sum, Count
from django.utils import timezone
from .models import Expense


def expenses(data):
    rows=Expense.objects.select_related('category','title','supplier')
    start,end=data.get('start'),data.get('end');today=timezone.localdate()
    period=data.get('period')
    if period=='today':start=end=today
    elif period=='yesterday':start=end=today-timedelta(days=1)
    elif period=='week':start=today-timedelta(days=today.weekday());end=start+timedelta(days=6)
    elif period=='month':start=today.replace(day=1);end=today.replace(day=calendar.monthrange(today.year,today.month)[1])
    elif period=='previous_month':end=today.replace(day=1)-timedelta(days=1);start=end.replace(day=1)
    elif period=='year':start=today.replace(month=1,day=1);end=today.replace(month=12,day=31)
    if start:rows=rows.filter(competence__gte=start)
    if end:rows=rows.filter(competence__lte=end)
    if data.get('q'):rows=rows.filter(Q(description__icontains=data['q'])|Q(counterparty__icontains=data['q'])|Q(supplier__legal_name__icontains=data['q']))
    if data.get('supplier'):rows=rows.filter(supplier=data['supplier'])
    if data.get('category'):
        code=data['category'].code;rows=rows.filter(Q(category__code=code)|Q(category__code__startswith=code+'.'))
    if data.get('cost_center'):rows=rows.filter(cost_center__icontains=data['cost_center'])
    status=data.get('status') or 'active'
    if status=='cancelled':rows=rows.filter(status='CANCELLED')
    elif status!='all':
        rows=rows.filter(status='ACTIVE')
        if status=='paid':rows=rows.filter(title__settled=F('title__amount'))
        elif status in ['pending','overdue']:rows=rows.filter(title__settled__lt=F('title__amount'))
        if status=='overdue':rows=rows.filter(title__due_date__lt=today)
        if status=='unclassified':rows=rows.filter(category__isnull=True)
        if status=='future':rows=rows.filter(competence__gt=today)
    return rows.order_by('-competence','-pk')


def expense_report(data):
    rows=expenses(data).filter(status='ACTIVE').order_by()
    groups=[];totals={'OPERATING':Decimal('0'),'FINANCIAL':Decimal('0'),'NONE':Decimal('0')}
    for row in rows.values('category_snapshot').annotate(total=Sum('amount'),count=Count('pk')).order_by('category_snapshot'):
        snapshot=row['category_snapshot'];path=snapshot.get('path',[])
        nature=snapshot.get('nature','NONE')
        label=f"{path[-1]['code']} · {path[-1]['name']}" if path else 'A classificar'
        groups.append({'label':label,'nature':nature,'amount':row['total'],'count':row['count']})
        totals[nature]+=row['total']
    return groups,totals
