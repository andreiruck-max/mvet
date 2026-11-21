"""Validated company context; group and secondary operations remain unavailable."""
from dataclasses import dataclass
from django.core.exceptions import PermissionDenied
from apps.core.models import Company
from .models import UserCompanyAccess


@dataclass(frozen=True)
class CompanyScope:
    company_ids: tuple
    group: bool = False

    def require_operation(self):
        if self.group or self.company_ids != (1,):
            raise PermissionDenied('Operações neste contexto ainda não estão disponíveis.')
        return 1


def resolve_scope(user, selection):
    """Never silently fall back from a rejected company to the primary company."""
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied('Usuário sem acesso.')
    group = selection == 'group'
    if not group:
        try:
            company_id = int(selection)
        except (TypeError, ValueError):
            raise PermissionDenied('Empresa inválida.')
        companies = Company.objects.filter(pk=company_id, active=True)
    else:
        companies = Company.objects.filter(active=True)
    if not user.is_superuser:
        grants = UserCompanyAccess.objects.filter(user=user, active=True)
        if group:
            grants = grants.filter(can_view_group=True)
        companies = companies.filter(pk__in=grants.values('company_id'))
    ids = tuple(companies.order_by('pk').values_list('pk', flat=True))
    if not ids:
        raise PermissionDenied('Sem acesso ao contexto empresarial solicitado.')
    return CompanyScope(ids, group)
