"""Current list prices; historical sales are never changed by pricing settings."""
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.accounts.access import master
from apps.core.models import Company
from apps.core.services import audit
from apps.inventory.services import domain_lock
from .models import Product


def sale_price(product, cost, default_markup):
    markup = product.markup if product.markup is not None else default_markup
    return (cost * (Decimal(1) + markup / Decimal(100))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


@transaction.atomic
def configure_pricing(*, actor, markup, product_id=None):
    master(actor)
    if markup is not None and (not isinstance(markup, Decimal) or not markup.is_finite()):
        raise ValidationError('Informe markup decimal válido.')
    domain_lock()
    obj = Product.objects.select_for_update().get(pk=product_id) if product_id else Company.objects.select_for_update().get(pk=1)
    field = 'markup' if product_id else 'default_markup'
    before = {field: str(getattr(obj, field))}
    setattr(obj, field, markup)
    obj.full_clean()
    obj.save(update_fields=[field])
    audit(actor, obj, 'configure_pricing', before, {field: str(markup)})
    return obj


def retail_location():
    from apps.inventory.models import StockLocation
    from apps.inventory.selectors import selected_location
    location = StockLocation.objects.filter(name__in=['Estoque Mercadovet', 'Mercadovet'], active=True).first()
    if location:
        return location
    location, _ = selected_location({})
    return location if location and 'full' not in location.name.casefold() else None
