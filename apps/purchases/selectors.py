from datetime import timedelta
from django.db.models import Q, Sum, Count, Max
from django.utils import timezone
from .models import Purchase, PurchaseItem, PurchaseInstallment

def purchases(data):
    rows=Purchase.objects.select_related('supplier','location')
    if data.get('q'):
        q=data['q'];rows=rows.filter(Q(document__icontains=q)|Q(items__sku_snapshot__icontains=q)|Q(items__name_snapshot__icontains=q)|Q(items__product__sku__icontains=q)|Q(items__product__name__icontains=q)).distinct()
    for field in ['supplier','location','status']:
        if data.get(field):rows=rows.filter(**{field:data[field]})
    start,end=data.get('start'),data.get('end');today=timezone.localdate();period=data.get('period')
    if period=='today':start=end=today
    elif period=='yesterday':start=end=today-timedelta(days=1)
    elif period=='week':start=today-timedelta(days=today.weekday());end=today
    elif period=='month':start=today.replace(day=1);end=today
    elif period=='previous_month':end=today.replace(day=1)-timedelta(days=1);start=end.replace(day=1)
    elif period=='year':start=today.replace(month=1,day=1);end=today
    if start:rows=rows.filter(date__gte=start)
    if end:rows=rows.filter(date__lte=end)
    # A single installment must satisfy the complete due/status filter.
    if data.get('due_start') or data.get('due_end') or data.get('pending'):
        installments=PurchaseInstallment.objects.all()
        if data.get('due_start'):installments=installments.filter(due_date__gte=data['due_start'])
        if data.get('due_end'):installments=installments.filter(due_date__lte=data['due_end'])
        if data.get('pending'):installments=installments.filter(status='PENDING',purchase__status__in=['ORDERED','RECEIVED'])
        if data.get('pending')=='overdue':installments=installments.filter(due_date__lt=today)
        rows=rows.filter(pk__in=installments.values('purchase_id'))
    return rows.order_by(data.get('sort') or '-date','-pk')

def supplier_report(supplier):
    orders=Purchase.objects.filter(supplier=supplier,status__in=['ORDERED','RECEIVED'])
    summary=orders.aggregate(total=Sum('total'),count=Count('pk'),last=Max('date'))
    summary['average']=summary['total']/summary['count'] if summary['count'] else None
    prices=PurchaseItem.objects.filter(purchase__supplier=supplier,purchase__status='RECEIVED').select_related('purchase','product').order_by('-purchase__received_date','-pk')
    outstanding=PurchaseInstallment.objects.filter(purchase__in=orders,status='PENDING').select_related('purchase').order_by('due_date','pk')
    summary['outstanding']=outstanding.aggregate(total=Sum('amount'))['total']
    return summary,prices,outstanding
