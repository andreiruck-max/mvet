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


class CompanyContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from django.conf import settings
        if not getattr(settings, 'COMPANY_CONTEXT_ENABLED', False) or not request.user.is_authenticated:
            return None
        name = request.resolver_match.url_name
        if name in {'login', 'logout', 'company_context'}:
            return None
        if request.user.is_superuser and name in {'company_registry','company_registry_edit','company_user_access','user_access','user_access_list','employee_new','employee_password'}:
            return None
        scope = resolve_scope(request.user, request.session.get('company_selection', '1'))
        # Legacy routes cannot serve secondary/group data before tenant migration.
        scope.require_operation()
        request.company_scope = scope
        request.user._mvet_company_scope = scope


def context_view(request):
    from django.conf import settings
    from django.http import Http404
    from django.shortcuts import render, redirect
    if not getattr(settings, 'COMPANY_CONTEXT_ENABLED', False):
        raise Http404
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    if request.method == 'POST':
        selection = request.POST.get('company', '')
        scope = resolve_scope(request.user, selection)
        request.session['company_selection'] = 'group' if scope.group else str(scope.company_ids[0])
        return redirect('company_context')
    if request.method != 'GET':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET','POST'])
    companies = Company.objects.filter(active=True)
    if not request.user.is_superuser:
        companies = companies.filter(pk__in=UserCompanyAccess.objects.filter(user=request.user,active=True).values('company_id'))
    try:
        resolve_scope(request.user,'group')
        group_allowed = True
    except PermissionDenied:
        group_allowed = False
    return render(request, 'accounts/company_context.html', {'scope_companies':companies,
        'group_allowed':group_allowed,'selection':request.session.get('company_selection','1')})


def template_context(request):
    from django.conf import settings
    return {'company_context_enabled': getattr(settings, 'COMPANY_CONTEXT_ENABLED', False),
            'company_context_selection': request.session.get('company_selection', '1')}
