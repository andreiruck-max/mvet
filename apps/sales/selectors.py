from datetime import timedelta
from django.db.models import Q
from django.utils import timezone
from .models import Sale

def sales(data):
    rows=Sale.objects.select_related('channel')
    if data.get('q'):rows=rows.filter(Q(invoice_number__icontains=data['q'])|Q(items__product__sku__icontains=data['q'])|Q(items__product__name__icontains=data['q'])|Q(items__sku_snapshot__icontains=data['q'])|Q(items__name_snapshot__icontains=data['q'])).distinct()
    for field in ['channel','status']:
        if data.get(field):rows=rows.filter(**{field:data[field]})
    start,end=data.get('start'),data.get('end')
    today=timezone.localdate();period=data.get('period')
    if period=='today':start=end=today
    elif period=='yesterday':start=end=today-timedelta(days=1)
    elif period=='week':start=today-timedelta(days=today.weekday());end=today
    elif period=='month':start=today.replace(day=1);end=today
    elif period=='previous_month':end=today.replace(day=1)-timedelta(days=1);start=end.replace(day=1)
    elif period=='year':start=today.replace(month=1,day=1);end=today
    if start:rows=rows.filter(date__gte=start)
    if end:rows=rows.filter(date__lte=end)
    return rows.order_by(data.get('sort') or '-date','-pk')
