from decimal import Decimal
from django.core.exceptions import PermissionDenied
from django.db import transaction
from .models import AuditLog, Company

def require(actor, permission):
    if not actor or not actor.is_active or not actor.has_perm(permission):
        raise PermissionDenied

def audit(actor, obj, operation, before=None, after=None):
    return AuditLog.objects.create(actor=actor, entity=obj._meta.label, entity_id=str(obj.pk),
        operation=operation, before=before or {}, after=after or {})

@transaction.atomic
def update_company(*, actor, name, minimum_margin):
    require(actor, "core.manage_configuration")
    if not isinstance(minimum_margin, Decimal):
        from django.core.exceptions import ValidationError
        raise ValidationError("Margem deve ser Decimal.")
    company = Company.objects.select_for_update().get(pk=1)
    before = {"name": company.name, "minimum_margin": str(company.minimum_margin)}
    company.name = name
    company.minimum_margin = minimum_margin
    company.full_clean()
    company.save(update_fields=["name", "minimum_margin", "updated_at"])
    audit(actor, company, "update_configuration", before,
          {"name": company.name, "minimum_margin": str(company.minimum_margin)})
    return company
