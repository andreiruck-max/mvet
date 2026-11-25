"""Access to a single company's tax rules, including setup before activation."""
from django.conf import settings
from django.core.exceptions import PermissionDenied

from apps.accounts.access import master
from apps.accounts.company_access import has_company_permission
from apps.accounts.company_context import resolve_scope
from apps.core.models import Company
from apps.core.services import require
from .models import Sale


def require_tax_management(actor, company_id, *, retroactive=False):
    scope = getattr(actor, '_mvet_company_scope', None)
    if scope is not None:
        # While operations are primary-only, preparation starts in the individual
        # admin area. Never interpret Group as permission to write both companies.
        scope.require_operation()
    permissions = ['core.manage_taxes']
    if retroactive:
        permissions.append('core.retroactive_taxes')
    if not getattr(settings, 'COMPANY_CONTEXT_ENABLED', False):
        if company_id != 1:
            raise PermissionDenied
        for permission in permissions:
            require(actor, permission)
        return
    if company_id == 1:
        (scope or resolve_scope(actor, '1')).require_operation()
        if not all(has_company_permission(actor, company_id, perm) for perm in permissions):
            raise PermissionDenied
        return

    master(actor)
    # This administrative exception is limited to tax rules of unused companies.
    # It must never be used for operations or historical recalculation.
    if not Company.objects.filter(pk=company_id, active=False).exists() or Sale.objects.filter(company_id=company_id).exists():
        raise PermissionDenied('A preparação exige empresa inativa e sem vendas.')
