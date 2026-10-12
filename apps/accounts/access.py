from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Permission
from django.contrib.auth.forms import UserCreationForm, SetPasswordForm
from django.db.models import Q
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from apps.core.services import audit
from .models import AccessPolicy
from .permissions import LABELS
from .catalog import permission_groups, PROFILES


def master(actor):
    if not actor.is_active or not actor.is_superuser:
        raise PermissionDenied


def choices():
    return [('core.'+p.codename, LABELS.get(p.codename, p.name)) for p in
        Permission.objects.filter(content_type__app_label='core').exclude(codename__startswith='add_').exclude(codename__startswith='delete_').exclude(codename__startswith='change_').exclude(codename='view_company').order_by('name')]


class AccessForm(forms.Form):
    first_name = forms.CharField(label='Nome', max_length=150, required=False)
    last_name = forms.CharField(label='Sobrenome', max_length=150, required=False)
    email = forms.EmailField(label='E-mail', required=False)
    active = forms.BooleanField(label='Usuário ativo', required=False)
    permissions = forms.MultipleChoiceField(label='Permissões permitidas', required=False, widget=forms.CheckboxSelectMultiple)
    revision = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['permissions'].choices = choices()


@transaction.atomic
def save_access(*, actor, user_id, active, permissions, revision, first_name=None, last_name=None, email=None):
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
    before = {'rules': policy.rules, 'active': user.is_active, 'revision': policy.revision,
              'name':user.get_full_name(), 'email':user.email}
    policy.rules = {code: code in permissions for code in codes}
    policy.rules['__complete__'] = True
    policy.revision += 1; policy.save()
    user.is_active = active
    for field, value in [('first_name',first_name),('last_name',last_name),('email',email)]:
        if value is not None: setattr(user, field, value)
    user.full_clean(exclude=['password'])
    user.save(update_fields=['is_active','first_name','last_name','email'])
    audit(actor, user, 'set_access_policy', before, {'rules': policy.rules, 'active': active, 'revision': policy.revision,
          'name':user.get_full_name(), 'email':user.email})


@login_required
@require_http_methods(['GET', 'POST'])
def users(request, pk=None):
    master(request.user)
    if pk is None:
        rows = User.objects.order_by('username')
        if request.GET.get('q'):
            q=request.GET['q'];rows=rows.filter(Q(username__icontains=q)|Q(first_name__icontains=q)|Q(last_name__icontains=q)|Q(email__icontains=q))
        if request.GET.get('status') in ('active','inactive'):
            rows=rows.filter(is_active=request.GET['status']=='active')
        return render(request, 'accounts/users.html', {'page': Paginator(rows, 30).get_page(request.GET.get('page'))})
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser: raise PermissionDenied
    policy = AccessPolicy.objects.filter(user=user).first()
    form = AccessForm(request.POST if request.method == 'POST' else None, initial={
        'active': user.is_active, 'revision': policy.revision if policy else 0,
        'first_name':user.first_name, 'last_name':user.last_name, 'email':user.email,
        'permissions': [code for code, _ in choices() if user.has_perm(code)]})
    if request.method == 'POST' and form.is_valid():
        try: save_access(actor=request.user, user_id=pk, **form.cleaned_data)
        except ValidationError as exc: form.add_error(None, exc)
        else:
            messages.success(request, 'Acessos salvos. Valem a partir da próxima requisição do usuário.')
            return redirect('user_access', pk=pk)
    from apps.core.models import AuditLog
    history=AuditLog.objects.filter(entity=user._meta.label, entity_id=str(user.pk),
        operation__in=['set_access_policy','create_employee','reset_employee_password']).select_related('actor')[:10]
    return render(request, 'accounts/access.html', {'form': form, 'target': user,
        'permission_groups':permission_groups(form), 'profiles':PROFILES, 'history':history})


class EmployeeForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        fields = ('username','first_name','last_name','email')


@login_required
@require_http_methods(['GET','POST'])
def employee_new(request):
    master(request.user)
    form = EmployeeForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user=form.save(commit=False)
            user.is_staff=False;user.is_superuser=False;user.save()
            AccessPolicy.objects.create(user=user, rules={'__complete__':True})
            audit(request.user,user,'create_employee',after={'username':user.username,'active':user.is_active})
        messages.success(request,'Funcionário cadastrado sem acesso aos módulos. Defina as permissões abaixo.')
        return redirect('user_access',pk=user.pk)
    return render(request,'accounts/employee_form.html',{'form':form,'title':'Cadastrar funcionário','button':'Cadastrar e definir acessos'})


@login_required
@require_http_methods(['GET','POST'])
def employee_password(request, pk):
    master(request.user)
    user=get_object_or_404(User,pk=pk)
    if user.is_superuser: raise PermissionDenied
    form=SetPasswordForm(user, request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            locked=User.objects.select_for_update().get(pk=pk)
            if locked.is_superuser: raise PermissionDenied
            locked.set_password(form.cleaned_data['new_password1']);locked.save(update_fields=['password'])
            audit(request.user,locked,'reset_employee_password')
        messages.success(request,'Senha redefinida. As sessões anteriores deste funcionário serão encerradas.')
        return redirect('user_access',pk=pk)
    return render(request,'accounts/employee_form.html',{'form':form,'target':user,'title':'Redefinir senha de '+user.username,'button':'Redefinir senha'})
