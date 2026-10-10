import re
from django.db.models import Q
from django.utils import timezone
from .models import Contact
from .services import access

def contacts(actor):
    access(actor)
    rows=Contact.objects.select_related('owner')
    return rows if actor.is_superuser else rows.filter(owner=actor)

def filtered(actor,data):
    rows=contacts(actor)
    if data.get('q'):
        q=data['q'].strip();digits=re.sub(r'\D','',q)
        query=Q(name__icontains=q)|Q(email__icontains=q)|Q(company__icontains=q)|Q(city__icontains=q)
        if digits:query|=Q(phone__contains=digits)
        rows=rows.filter(query)
    for field in ('owner','segment','origin','state'):
        if data.get(field):rows=rows.filter(**{field:data[field]})
    if data.get('city'):rows=rows.filter(city__icontains=data['city'])
    if data.get('result'):rows=rows.filter(last_result=data['result'])
    if data.get('start'):rows=rows.filter(next_date__gte=data['start'])
    if data.get('end'):rows=rows.filter(next_date__lte=data['end'])
    if data.get('overdue'):rows=rows.filter(next_date__lt=timezone.localdate(),state__in=['ACTIVE','WAITING','PAUSED'])
    return rows

def decorate(rows):
    today=timezone.localdate()
    for obj in rows:
        obj.days=(obj.next_date-today).days if obj.next_date else None
        obj.overdue_days=-obj.days if obj.days is not None and obj.days<0 else 0
        obj.wait_days=(today-timezone.localdate(obj.last_at)).days if obj.last_at else 0
        obj.bucket='Atrasados' if obj.overdue_days else ('Hoje' if obj.days==0 else 'Próximos')
    return rows
