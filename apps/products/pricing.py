"""Current list prices; historical sales are never changed by pricing settings."""
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.accounts.access import master
from apps.core.models import Company
from apps.core.services import audit
from apps.inventory.services import domain_lock, _require_owner
from .models import Product
from .policies import commercial_values, sync_primary_policy


def sale_price(product, cost, default_markup, *, company_id=1):
    values = commercial_values(product,company_id=company_id)
    if values['fixed_sale_price'] is not None:
        return values['fixed_sale_price']
    markup = values['markup'] if values['markup'] is not None else default_markup
    return (cost * (Decimal(1) + markup / Decimal(100))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


@transaction.atomic
def configure_pricing(*, actor, markup, product_id=None, company_id=1):
    _require_owner(company_id,actor)
    master(actor)
    if markup is not None and (not isinstance(markup, Decimal) or not markup.is_finite()):
        raise ValidationError('Informe markup decimal válido.')
    domain_lock()
    obj = Product.objects.select_for_update().get(pk=product_id) if product_id else Company.objects.select_for_update().get(pk=company_id)
    field = 'markup' if product_id else 'default_markup'
    before = {field: str(getattr(obj, field))}
    setattr(obj, field, markup)
    obj.full_clean()
    obj.save(update_fields=[field])
    if product_id: sync_primary_policy(obj)
    audit(actor, obj, 'configure_pricing', before, {field: str(markup)})
    return obj


@transaction.atomic
def configure_fixed_price(*, actor, product_id, price, company_id=1):
    _require_owner(company_id,actor)
    master(actor)
    if price is not None:
        from apps.inventory.services import number
        number(price, Decimal('.01'), zero=True)
    domain_lock()
    obj = Product.objects.select_for_update().get(pk=product_id)
    before = {'fixed_sale_price': str(obj.fixed_sale_price)}
    obj.fixed_sale_price = price
    obj.full_clean()
    obj.save(update_fields=['fixed_sale_price'])
    sync_primary_policy(obj)
    audit(actor, obj, 'configure_fixed_price', before, {'fixed_sale_price': str(price)})
    return obj


def retail_location():
    from apps.inventory.models import StockLocation
    from apps.inventory.selectors import selected_location
    location = StockLocation.objects.filter(name__in=['Estoque Mercadovet', 'Mercadovet'], active=True).first()
    if location:
        return location
    location, _ = selected_location({})
    return location if location and 'full' not in location.name.casefold() else None
