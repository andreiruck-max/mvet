from decimal import Decimal
from django.db.models import Q, F
from apps.products.models import Product
from .services import _require_owner

def search_products(rows, query):
    query = query.strip()
    if not query:
        return rows
    if query.isdecimal() or rows.filter(sku__iexact=query).exists():
        return rows.filter(sku__iexact=query)
    return rows.filter(Q(name__icontains=query) | Q(sku__istartswith=query))


def selected_location(params, *, company_id=1):
    _require_owner(company_id)
    from apps.core.models import Company
    from .models import StockLocation
    locations = list(StockLocation.objects.all())
    raw = params.get('location', '')
    if raw:
        match = next((loc for loc in locations if str(loc.pk) == raw), None)
        if match is None:
            from django.core.exceptions import ValidationError
            raise ValidationError('Depósito inválido.')
        return match, locations
    default = Company.objects.filter(pk=company_id).values_list('default_stock_location_id', flat=True).first()
    chosen = next((loc for loc in locations if loc.pk == default and loc.active), None)
    chosen = chosen or next((loc for loc in locations if loc.name == 'Estoque Mercadovet' and loc.active), None)
    return chosen or next((loc for loc in locations if loc.active), None), locations


def catalog(params, location=None, *, company_id=1):
    _require_owner(company_id)
    from django.db.models import Case, When, Value, DecimalField, OuterRef, Subquery, IntegerField
    from django.db.models.functions import Cast, Coalesce
    from .models import StockBalance
    rows = Product.objects.select_related('brand', 'category')
    rows = search_products(rows, params.get('q', ''))
    if location is None:
        location, _ = selected_location(params,company_id=company_id)
    field = DecimalField(max_digits=18, decimal_places=4)
    balances = StockBalance.objects.filter(company_id=company_id,product_id=OuterRef('pk'), location_id=location.pk if location else None)
    from apps.products.models import CompanyProductPolicy
    from django.db.models import Prefetch
    rows = rows.prefetch_related(Prefetch("company_policies", queryset=CompanyProductPolicy.objects.filter(company_id=company_id), to_attr="_commercial_policies"))
    policies = CompanyProductPolicy.objects.filter(company_id=company_id,product_id=OuterRef('pk'))
    rows = rows.annotate(commercial_minimum=Coalesce(Subquery(policies.values('minimum')[:1]), F('minimum'),output_field=field))
    rows = rows.annotate(stock_cost=Coalesce(Subquery(balances.values('average_cost')[:1]), Value(Decimal(0)), output_field=DecimalField(max_digits=24, decimal_places=6)))
    rows = rows.annotate(stock_quantity=Coalesce(Subquery(balances.values('quantity')[:1]), Value(Decimal(0)), output_field=field))
    if params.get('status', 'active') == 'active': rows = rows.filter(active=True)
    if params.get('status') == 'inactive': rows = rows.filter(active=False)
    if params.get('positive', '1') == '1': rows = rows.filter(stock_quantity__gt=0)
    if params.get('low') == '1': rows = rows.filter(kind='SIMPLE', stock_quantity__lte=F('commercial_minimum'))
    order = params.get('sort', 'sku')
    if order not in {'name', 'sku', 'quantity', '-quantity'}: order = 'sku'
    if order == 'sku':
        return order_by_sku(rows)
    if order in {'quantity', '-quantity'}: order = order.replace('quantity', 'stock_quantity')
    return rows.order_by(order, 'pk')


def location_values(product, *, company_id=1):
    _require_owner(company_id)
    return {b.location_id: b.value for b in product.balances.all() if b.company_id == company_id}


def stock_totals(locations, *, company_id=1):
    _require_owner(company_id)
    from django.db.models import Sum
    from .models import StockBalance
    values = dict(StockBalance.objects.filter(company_id=company_id,product__kind='SIMPLE')
                  .values('location_id').annotate(total=Sum('value')).values_list('location_id','total'))
    total = sum(values.values(), Decimal(0))
    return [{'location': loc, 'value': values.get(loc.pk,Decimal(0))} for loc in locations], total


def kit_summary(product, *, company_id=1):
    _require_owner(company_id)
    parts=list(product.components.select_related('component'))
    available=min((int(i.component.quantity//i.quantity) for i in parts),default=0)
    cost=sum((i.component.average_cost*i.quantity for i in parts),Decimal('0'))
    return parts,available,cost


def order_by_sku(rows):
    from django.db.models import Case, When, Value, DecimalField, IntegerField
    from django.db.models.functions import Cast
    # Numeric(60,0) covers the entire SKU field without integer overflow.
    rows = rows.annotate(sku_group=Case(When(sku__regex=r'^[0-9]+$', then=Value(0)), default=Value(1), output_field=IntegerField()),
        sku_number=Case(When(sku__regex=r'^[0-9]+$', then=Cast('sku', DecimalField(max_digits=60, decimal_places=0))), default=None))
    return rows.order_by('sku_group', 'sku_number', 'sku', 'pk')
