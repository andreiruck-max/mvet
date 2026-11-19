"""Explicit grants for the future company context. Does not replace legacy routes yet."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from apps.core.models import Company
from apps.core.services import audit
from .access import master, choices
from .models import UserCompanyAccess


def has_company_permission(user, company_id, permission):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if not Company.objects.filter(pk=company_id, active=True).exists():
        return False
    if user.is_superuser:
        return True
    grant = UserCompanyAccess.objects.filter(user=user, company_id=company_id, active=True).first()
    if not grant:
        return False
    if grant.inherit_legacy and company_id == 1:
        return user.has_perm(permission)
    return grant.rules.get(permission) is True


class CompanyAccessForm(forms.Form):
    active = forms.BooleanField(label='Vínculo ativo', required=False)
    inherit_legacy = forms.BooleanField(label='Preservar permissões atuais da Mercadovet', required=False)
    can_view_group = forms.BooleanField(label='Autorizar esta empresa na futura visão Grupo', required=False)
    permissions = forms.MultipleChoiceField(label='Permissões explícitas nesta empresa',
        required=False, widget=forms.CheckboxSelectMultiple)
    revision = forms.IntegerField(widget=forms.HiddenInput, initial=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['permissions'].choices = choices()


@transaction.atomic
def save_company_access(*, actor, user_id, company_id, active, inherit_legacy, can_view_group,
                        permissions, revision):
    master(actor)
    # Lock the user first, also serializing concurrent creation of a missing grant.
    user = get_user_model().objects.select_for_update().get(pk=user_id)
    if user.is_superuser:
        raise ValidationError('O master administra o grupo; seus acessos não são editados aqui.')
    company = Company.objects.get(pk=company_id)
    if inherit_legacy and company.pk != 1:
        raise ValidationError('Somente a Mercadovet pode preservar as permissões legadas.')
    allowed = {code for code, _ in choices()}
    if set(permissions) - allowed:
        raise ValidationError('Permissão inválida.')
    grant = UserCompanyAccess.objects.filter(user=user, company=company).first()
    grant = grant or UserCompanyAccess(user=user, company=company)
    if grant.revision != revision:
        raise ValidationError('Vínculo alterado por outra sessão. Reabra a tela.')
    fields = ('active', 'inherit_legacy', 'can_view_group', 'rules', 'revision')
    before = {key: getattr(grant, key) for key in fields}
    grant.active, grant.inherit_legacy, grant.can_view_group = active, inherit_legacy, can_view_group
    grant.rules = {code: True for code in permissions}
    grant.revision += 1
    grant.full_clean()
    grant.save()
    audit(actor, grant, 'company_access_saved', before,
          dict(user_id=user.pk, company_id=company.pk, **{key: getattr(grant, key) for key in fields}))
    return grant


@login_required
@require_http_methods(['GET', 'POST'])
def access(request, user_id, company_id):
    master(request.user)
    user = get_object_or_404(get_user_model(), pk=user_id, is_superuser=False)
    company = get_object_or_404(Company, pk=company_id)
    grant = UserCompanyAccess.objects.filter(user=user, company=company).first()
    initial = {key: getattr(grant, key) for key in ('active', 'inherit_legacy', 'can_view_group', 'revision')} if grant else {}
    initial['permissions'] = [key for key, value in grant.rules.items() if value is True] if grant else []
    form = CompanyAccessForm(request.POST if request.method == 'POST' else None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            save_company_access(actor=request.user, user_id=user.pk, company_id=company.pk, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Vínculo empresarial salvo para a próxima etapa de escopo.')
            return redirect('company_user_access', user_id=user.pk, company_id=company.pk)
    return render(request, 'accounts/company_access.html', {'form': form, 'target': user,
        'company': company, 'companies': Company.objects.order_by('pk')})
