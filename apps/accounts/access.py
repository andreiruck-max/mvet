from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from apps.core.services import audit
from .models import AccessPolicy
from .permissions import LABELS


def master(actor):
    if not actor.is_active or not actor.is_superuser:
        raise PermissionDenied


def choices():
    return [('core.'+p.codename, LABELS.get(p.codename, p.name)) for p in
        Permission.objects.filter(content_type__app_label='core').exclude(codename__startswith='add_').exclude(codename__startswith='delete_').exclude(codename__startswith='change_').exclude(codename='view_company').order_by('name')]


class AccessForm(forms.Form):
    active = forms.BooleanField(label='Usuário ativo', required=False)
    permissions = forms.MultipleChoiceField(label='Permissões permitidas', required=False, widget=forms.CheckboxSelectMultiple)
    revision = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['permissions'].choices = choices()


@transaction.atomic
def save_access(*, actor, user_id, active, permissions, revision):
    master(actor)
    user = User.objects.select_for_update().get(pk=user_id)
    if user.is_superuser:
        raise ValidationError('Contas master são protegidas. Use a administração de usuários.')
    policy, _ = AccessPolicy.objects.get_or_create(user=user)
    if policy.revision != revision:
        raise ValidationError('Permissões alteradas por outra sessão. Reabra a tela.')
    codes = {code for code, _ in choices()}
    if set(permissions)-codes:
        raise ValidationError('Permissão inválida.')
    before = {'rules': policy.rules, 'active': user.is_active, 'revision': policy.revision}
    policy.rules = {code: code in permissions for code in codes}
    policy.revision += 1; policy.save()
    user.is_active = active; user.save(update_fields=['is_active'])
    audit(actor, user, 'set_access_policy', before, {'rules': policy.rules, 'active': active, 'revision': policy.revision})


@login_required
@require_http_methods(['GET', 'POST'])
def users(request, pk=None):
    master(request.user)
    if pk is None:
        rows = User.objects.order_by('username')
        if request.GET.get('q'): rows = rows.filter(username__icontains=request.GET['q'])
        return render(request, 'accounts/users.html', {'page': Paginator(rows, 30).get_page(request.GET.get('page'))})
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser: raise PermissionDenied
    policy = AccessPolicy.objects.filter(user=user).first()
    form = AccessForm(request.POST if request.method == 'POST' else None, initial={
        'active': user.is_active, 'revision': policy.revision if policy else 0,
        'permissions': [code for code, _ in choices() if user.has_perm(code)]})
    if request.method == 'POST' and form.is_valid():
        try: save_access(actor=request.user, user_id=pk, **form.cleaned_data)
        except ValidationError as exc: form.add_error(None, exc)
        else:
            messages.success(request, 'Acessos salvos. Valem a partir da próxima requisição do usuário.')
            return redirect('user_access', pk=pk)
    return render(request, 'accounts/access.html', {'form': form, 'target': user})
