"""Company commercial settings; stock and historical sale costs are never modified."""
from .models import CompanyProductPolicy

FIELDS = ('minimum', 'markup', 'fixed_sale_price')


def sync_primary_policy(product):
    """Called under the product/domain lock by legacy write services, in their transaction."""
    return CompanyProductPolicy.objects.update_or_create(company_id=1, product=product,
        defaults={field:getattr(product,field) for field in FIELDS})[0]


def commercial_values(product, *, company_id=1):
    from apps.inventory.services import _require_owner
    _require_owner(company_id)
    prefetched = getattr(product, '_commercial_policies', None)
    if prefetched is not None:
        policy = next((row for row in prefetched if row.company_id == company_id), None)
    else:
        policy = CompanyProductPolicy.objects.filter(company_id=company_id,product=product).first() if product.pk else None
    # Transitional compatibility for unsaved/new products and legacy fixtures only.
    # Never use the shared legacy fields as a fallback for another company.
    return {field:getattr(policy if policy is not None else product,field) for field in FIELDS}
