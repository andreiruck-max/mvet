"""Company registry foundation; secondary operations remain disabled by DB constraint."""
import re
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from apps.accounts.access import master
from .models import Company, AuditLog
from .services import audit


class CompanyRegistryForm(forms.Form):
    name = forms.CharField(label="Razão social", max_length=180)
    trade_name = forms.CharField(label="Nome fantasia", max_length=180, required=False)
    cnpj = forms.CharField(label="CNPJ (preencher quando disponível)", max_length=18, required=False)
    revision = forms.IntegerField(widget=forms.HiddenInput, initial=0)

    def clean_cnpj(self):
        value = self.cleaned_data['cnpj'].strip()
        if value and not re.fullmatch(r'[0-9./-]+', value):
            raise ValidationError('CNPJ deve conter apenas dígitos e separadores usuais.')
        value = re.sub(r'[./-]', '', value)
        if value and len(value) != 14:
            raise ValidationError('Informe 14 dígitos para o CNPJ.')
        return value or None


@transaction.atomic
def save_company(*, actor, company_id=None, name, trade_name='', cnpj=None, revision=0):
    master(actor)
    company = (Company.objects.select_for_update().get(pk=company_id)
               if company_id is not None else Company(active=False))
    if company.revision != revision:
        raise ValidationError('Cadastro alterado por outra sessão. Reabra a tela.')
    if company.cnpj and company.cnpj != cnpj:
        raise ValidationError('O CNPJ identifica a empresa e não pode ser trocado por esta tela.')
    before = {k: getattr(company, k) for k in ('name', 'trade_name', 'cnpj', 'active', 'revision')}
    company.name, company.trade_name, company.cnpj = name, trade_name, cnpj or None
    company.revision += 1
    company.full_clean()
    company.save()
    audit(actor, company, 'company_registry_saved', before,
          {k: getattr(company, k) for k in before})
    return company


@login_required
@require_http_methods(['GET', 'POST'])
def registry(request, pk=None):
    master(request.user)
    company = get_object_or_404(Company, pk=pk) if pk is not None else None
    form = CompanyRegistryForm(request.POST if request.method == 'POST' else None,
        initial={k: getattr(company, k) for k in ('name', 'trade_name', 'cnpj', 'revision')} if company else None)
    if request.method == 'POST' and form.is_valid():
        try:
            company = save_company(actor=request.user, company_id=pk, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Cadastro salvo. Empresas secundárias continuam sem operações nesta fase.')
            return redirect('company_registry_edit', pk=company.pk)
    history = AuditLog.objects.filter(entity='core.Company', operation='company_registry_saved')[:10]
    return render(request, 'core/companies.html', {'form': form, 'selected_company': company,
        'companies': Company.objects.order_by('pk'), 'history': history})
