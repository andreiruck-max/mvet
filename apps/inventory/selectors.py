from decimal import Decimal
from django.db.models import Q, F
from apps.products.models import Product

def catalog(params):
    rows=Product.objects.select_related('brand','category')
    query=params.get('q','').strip()
    if query:rows=rows.filter(Q(sku__icontains=query)|Q(name__icontains=query))
    if params.get('status','active')=='active': rows=rows.filter(active=True)
    if params.get('status')=='inactive':rows=rows.filter(active=False)
    if params.get('low')=='1': rows=rows.filter(kind='SIMPLE',quantity__lte=F('minimum'))
    order=params.get('sort','name')
    if order not in {'name','sku','quantity','-quantity'}:order='name'
    return rows.order_by(order,'pk')

def kit_summary(product):
    parts=list(product.components.select_related('component'))
    available=min((int(i.component.quantity//i.quantity) for i in parts),default=0)
    cost=sum((i.component.average_cost*i.quantity for i in parts),Decimal('0'))
    return parts,available,cost
