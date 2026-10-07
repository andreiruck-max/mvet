"""Read-only replenishment estimates; never place orders or change product status."""
from datetime import timedelta
from decimal import Decimal, ROUND_UP
from django import forms
from django.db.models import Max, Sum
from django.utils import timezone
from apps.purchases.models import PurchaseItem
from .models import StockMovement, StockLocation
from .selectors import catalog


class PlanningForm(forms.Form):
    location = forms.ModelChoiceField(label='Depósito', queryset=StockLocation.objects.filter(active=True))
    zero_days = forms.IntegerField(label='Fora de linha após (dias zerado)', min_value=1, max_value=3650, initial=30)
    history_days = forms.IntegerField(label='Histórico de vendas (dias)', min_value=1, max_value=3650, initial=30)
    coverage_days = forms.IntegerField(label='Comprar para (dias)', min_value=1, max_value=365, initial=30)
    q = forms.CharField(label='SKU ou nome', required=False)
    show_excluded = forms.BooleanField(label='Mostrar fora de linha', required=False)


def purchase_plan(*, location, zero_days, history_days, coverage_days, q='', show_excluded=False, today=None):
    today = today or timezone.localdate()
    products = list(catalog({'positive': '0', 'q': q}, location).filter(kind='SIMPLE'))
    ids = [p.pk for p in products]
    moves = StockMovement.objects.filter(location=location, product_id__in=ids)
    # Actual recording time is intentional: a backdated adjustment happened now.
    latest = dict(moves.exclude(quantity=0).values('product_id').annotate(last=Max('operation__created_at')).values_list('product_id', 'last'))
    sales = dict(moves.filter(operation__kind='SALE_OUT', operation__reversal__isnull=True,
        operation__date__gte=today-timedelta(days=history_days-1), operation__date__lte=today)
        .values('product_id').annotate(qty=Sum('quantity')).values_list('product_id', 'qty'))
    incoming = dict(PurchaseItem.objects.filter(product_id__in=ids, moves_stock=True,
        purchase__location=location, purchase__status='ORDERED')
        .values('product_id').annotate(qty=Sum('quantity')).values_list('product_id', 'qty'))
    rows = []; excluded_count = 0; suggested_count = 0
    for product in products:
        last = latest.get(product.pk)
        days = max(0, (today-timezone.localdate(last)).days) if last else None
        excluded = product.stock_quantity == 0 and days is not None and days >= zero_days
        if excluded:
            excluded_count += 1
        sold = max(Decimal(0), -sales.get(product.pk, Decimal(0)))
        target = max(product.minimum, sold * Decimal(coverage_days) / Decimal(history_days))
        pending = incoming.get(product.pk, Decimal(0))
        suggested = Decimal(0) if excluded else max(Decimal(0), target-product.stock_quantity-pending).quantize(Decimal('.0001'), rounding=ROUND_UP)
        if suggested > 0:
            suggested_count += 1
        if excluded and not show_excluded:
            continue
        rows.append({'product': product, 'days': days, 'excluded': excluded, 'sold': sold,
                     'pending': pending, 'suggested': suggested})
    return rows, {'suggested_count': suggested_count, 'excluded_count': excluded_count, 'product_count': len(products)}
