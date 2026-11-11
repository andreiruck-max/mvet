from datetime import timedelta
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.accounts.access import master
from apps.finance.models import FinancialAccount
from apps.reporting.forms import PeriodForm
from .models import BlingBankAccount, BlingBankLink, BlingSchedule
from . import bank_services as services


class LinkForm(forms.ModelForm):
    class Meta:
        model = BlingBankLink
        fields = ['external','start_date','opening_balance','automatic']
        labels = {'external':'Conta correspondente no Bling'}
        widgets = {'start_date':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d')}
        localized_fields = ['opening_balance']
        help_texts = {'opening_balance':'Informe o saldo do Bling no início da data acima, antes dos movimentos do dia. Vazio permite ver o extrato, mas não comparar saldos.'}


@login_required
@permission_required('core.view_finance', raise_exception=True)
def settings(request, pk):
    master(request.user)
    account = get_object_or_404(FinancialAccount, pk=pk)
    obj = BlingBankLink.objects.filter(account=account).first()
    action = request.POST.get('action')
    form = LinkForm(request.POST if request.method == 'POST' and action == 'save' else None, instance=obj,
        initial={'start_date': max(account.opening_date,timezone.localdate().replace(day=1))} if not obj else None)
    if obj:
        form.fields['external'].disabled = True
    next_page = None
    if request.method == 'POST':
        try:
            if action == 'catalog':
                try: page = int(request.POST.get('page',1))
                except (ValueError,TypeError): raise ValidationError('Página inválida.')
                more = services.fetch_accounts(actor=request.user,page=page)
                next_page = page+1 if more else None
                messages.success(request,'Contas do Bling carregadas. Se a sua conta não apareceu, carregue a próxima página.')
            elif action == 'save' and form.is_valid():
                obj = services.configure(actor=request.user,account_id=pk,**form.cleaned_data)
                services.enqueue(actor=request.user,link_id=obj.pk,automatic=obj.automatic,start=obj.start_date,
                    end=min(timezone.localdate(),obj.start_date+timedelta(days=365)))
                messages.success(request,'Vínculo salvo. A importação será feita em segundo plano.')
                return redirect('bling_bank_statement',pk=pk)
        except (ValidationError,IntegrityError) as exc:
            form.add_error(None,exc if isinstance(exc,ValidationError) else 'Esta conta já possui vínculo. Reabra a tela.')
    return render(request,'integrations/bank_settings.html',dict(account=account,form=form,next_page=next_page))


def panel_context(request, account, *, compact=False):
    link = BlingBankLink.objects.filter(account=account).select_related('external','account').first()
    data = request.GET.copy()
    if not any(data.get(k) for k in ('period','start','end')): data['period']='month'
    form = PeriodForm(data); form.fields.pop('channel')
    result = None; page = None
    if link and form.is_valid():
        start,end = form.cleaned_data['start'],form.cleaned_data['end']
        result = services.comparison(link,start,end)
        entries = link.entries.filter(date__range=(start,min(end,timezone.localdate())))
        page = Paginator(entries,50).get_page(request.GET.get('page'))
        display=form.data.copy();display.update(start=start.isoformat(),end=end.isoformat());form.data=display
    run = link.runs.order_by('-pk').first() if link else None
    last = link.runs.filter(status='DONE').order_by('-finished_at').first() if link else None
    worker = BlingSchedule.objects.first()
    return dict(account=account,bank_link=link,bank_form=form,comparison=result,bank_page=page,bank_run=run,
        bank_last=last,bank_worker_online=worker.worker_online if worker else False,bank_compact=compact)


@login_required
@permission_required('core.view_finance', raise_exception=True)
def statement(request, pk):
    account = get_object_or_404(FinancialAccount,pk=pk)
    return render(request,'integrations/bank_statement.html',panel_context(request,account))


@login_required
@permission_required('core.view_finance', raise_exception=True)
def status(request, pk):
    account = get_object_or_404(FinancialAccount,pk=pk)
    context=panel_context(request,account,compact=request.GET.get('compact')=='1')
    run=context['bank_run']
    return JsonResponse({'busy':bool(run and run.status in services.ACTIVE),
        'html':render_to_string('integrations/bank_panel.html',context,request=request)})


@login_required
@require_POST
def refresh(request, pk):
    services.access(request.user)
    link=get_object_or_404(BlingBankLink,account_id=pk)
    automatic=request.POST.get('mode')=='automatic'
    try:
        if automatic:
            run=services.enqueue(actor=request.user,link_id=link.pk,automatic=True)
        else:
            form=PeriodForm(request.POST)
            if not form.is_valid(): raise ValidationError('Informe um período válido para atualizar o extrato.')
            run=services.enqueue(actor=request.user,link_id=link.pk,
                start=form.cleaned_data['start'],end=min(form.cleaned_data['end'],timezone.localdate()))
        return JsonResponse({'queued':run is not None})
    except ValidationError as exc:
        return JsonResponse({'error':'; '.join(exc.messages)},status=400)
