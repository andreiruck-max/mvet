from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import FinancialAccount as Account, FinancialTitle as Title, FinancialOperation as Operation, FinancialEntry as Entry
from . import forms, services, selectors


def check_read(user):
    if not user.has_perm('core.operate_finance') and not user.has_perm('core.view_finance'): raise PermissionDenied


def error(form, exc):
    form.add_error(None,'; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Registro duplicado ou inconsistente. Reabra e confira os dados.')


@login_required
def title_list(request):
    check_read(request.user)
    form=forms.FilterForm(request.GET or {'status':'pending'})
    rows=selectors.titles(form.cleaned_data) if form.is_valid() else Title.objects.none()
    return render(request,'finance/titles.html',{'form':form,'page':Paginator(rows,30).get_page(request.GET.get('page'))})


@login_required
@permission_required('core.operate_finance',raise_exception=True)
def title_new(request):
    form=forms.TitleForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        data=dict(form.cleaned_data);key=data.pop('key')
        try:
            title=services.create_title(actor=request.user,key=key,data=data)
            messages.success(request,'Título registrado. Ainda não houve movimento bancário.')
            return redirect('financial_title',pk=title.pk)
        except (ValidationError,IntegrityError) as exc: error(form,exc)
    return render(request,'finance/form.html',{'form':form,'title':'Novo título / crédito ou débito previsto','button':'Registrar título','help':'Compras e vendas confirmadas já geram títulos automaticamente. Não os cadastre novamente. Para movimentar dinheiro, registre e depois liquide. Empréstimos: separe principal patrimonial e juros em títulos distintos.'})


@login_required
def title_detail(request,pk):
    check_read(request.user)
    title=get_object_or_404(Title.objects.select_related('account','sale','purchase_installment__purchase'),pk=pk)
    settlement=forms.SettlementForm(initial={'principal':title.remaining,'actual':title.remaining,'account':title.account_id,'revision':title.revision})
    schedule=forms.ScheduleForm(initial={'due_date':title.due_date,'account':title.account_id,'notes':title.notes,'revision':title.revision})
    return render(request,'finance/title.html',{'title':title,'settlement':settlement,'schedule':schedule,'operations':title.operations.select_related('reversal').order_by('-pk'),'reverse_form':forms.ReverseForm()})


@login_required
@permission_required('core.operate_finance',raise_exception=True)
@require_POST
def title_action(request,pk,action):
    title=get_object_or_404(Title,pk=pk)
    form={'settle':forms.SettlementForm,'schedule':forms.ScheduleForm,'cancel':forms.ReverseForm}[action](request.POST)
    if form.is_valid():
        data=dict(form.cleaned_data)
        try:
            if action=='settle':
                data['account_id']=data.pop('account').pk
                services.settle(actor=request.user,title_id=pk,**data)
            elif action=='schedule': services.schedule_title(actor=request.user,pk=pk,**data)
            else: services.cancel_title(actor=request.user,pk=pk,reason=data['reason'])
            messages.success(request,'Operação financeira confirmada.')
            return redirect('financial_title',pk=pk)
        except (ValidationError,IntegrityError) as exc: error(form,exc)
    return render(request,'finance/form.html',{'form':form,'title':title.description,'button':'Confirmar','help':'Confira os dados e tente novamente.'},status=400)


@login_required
@permission_required('core.view_finance',raise_exception=True)
def account_list(request):
    return render(request,'finance/accounts.html',{'page':Paginator(Account.objects.all(),30).get_page(request.GET.get('page'))})


@login_required
@permission_required(['core.operate_finance','core.view_finance'],raise_exception=True)
def account_edit(request,pk=None):
    account=get_object_or_404(Account,pk=pk) if pk else None
    form=forms.AccountForm(request.POST or None,instance=account,initial={} if pk else {'opening_date':timezone.localdate()})
    if request.method=='POST' and form.is_valid():
        try:
            services.save_account(actor=request.user,data=form.cleaned_data,pk=pk)
            messages.success(request,'Conta salva.');return redirect('financial_accounts')
        except (ValidationError,IntegrityError) as exc: error(form,exc)
    return render(request,'finance/form.html',{'form':form,'title':'Editar conta' if pk else 'Nova conta financeira','button':'Salvar conta','help':'Saldo inicial é o saldo no início do dia escolhido. Não inclua novamente as operações já contidas nele.'})


@login_required
@permission_required(['core.operate_finance','core.view_finance'],raise_exception=True)
@require_POST
def account_delete(request,pk):
    get_object_or_404(Account,pk=pk)
    try:
        services.delete_account(actor=request.user,pk=pk);messages.success(request,'Conta sem histórico excluída; operação registrada na auditoria.')
    except ValidationError as exc: messages.error(request,'; '.join(exc.messages))
    return redirect('financial_accounts')


@login_required
@permission_required('core.operate_finance',raise_exception=True)
def transfer_new(request):
    form=forms.TransferForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        data=dict(form.cleaned_data);data['source_id']=data.pop('source').pk;data['destination_id']=data.pop('destination').pk
        try:
            op=services.transfer(actor=request.user,**data);return redirect('financial_operation',pk=op.pk)
        except (ValidationError,IntegrityError) as exc: error(form,exc)
    return render(request,'finance/form.html',{'form':form,'title':'Transferência entre contas','button':'Confirmar transferência','help':'A saída e a entrada são vinculadas. Não representam receita ou despesa. Data futura exige marcar Apenas prevista.'})


@login_required
def operation_detail(request,pk):
    check_read(request.user)
    op=get_object_or_404(Operation.objects.select_related('title','reversal','reversal_of'),pk=pk)
    return render(request,'finance/operation.html',{'operation':op,'entries':op.entries.select_related('account'),'form':forms.ReverseForm()})


@login_required
@permission_required('core.operate_finance',raise_exception=True)
@require_POST
def operation_action(request,pk,action):
    get_object_or_404(Operation,pk=pk)
    form=forms.ReverseForm(request.POST)
    if form.is_valid():
        try:
            if action=='post': services.post_transfer(actor=request.user,pk=pk,date=form.cleaned_data['date'])
            else: services.reverse(actor=request.user,pk=pk,**form.cleaned_data)
            messages.success(request,'Operação financeira confirmada.')
        except (ValidationError,IntegrityError) as exc: error(form,exc)
        else: return redirect('financial_operation',pk=pk)
    return render(request,'finance/form.html',{'form':form,'title':'Revisar operação financeira','button':'Confirmar'},status=400)


@login_required
@permission_required('core.view_finance',raise_exception=True)
def cash(request):
    form=forms.CashForm(request.GET or {'start':timezone.localdate(),'end':timezone.localdate()+timedelta(days=30)})
    rows=[];unallocated={}
    if form.is_valid():
        data=form.cleaned_data;rows,unallocated=selectors.daily_cash(data['start'],data['end'],data['account'].pk if data['account'] else None)
    return render(request,'finance/cash.html',{'form':form,'rows':rows,'unallocated':unallocated})


@login_required
@permission_required('core.view_finance',raise_exception=True)
def cash_api(request):
    form=forms.CashForm(request.GET)
    if not form.is_valid(): return JsonResponse({'errors':form.errors.get_json_data()},status=400)
    d=form.cleaned_data;rows,unallocated=selectors.daily_cash(d['start'],d['end'],d['account'].pk if d['account'] else None)
    return JsonResponse({'days':[{k:(v.pk if k=='account' else str(v)) for k,v in row.items()} for row in rows],'unallocated':{k:str(v) for k,v in unallocated.items()}})


@login_required
@permission_required('core.view_finance',raise_exception=True)
def day_detail(request,pk,date):
    from datetime import date as Date
    account=get_object_or_404(Account,pk=pk)
    try: day=Date.fromisoformat(date)
    except ValueError:
        from django.http import Http404
        raise Http404
    rows=Entry.objects.filter(account=account,operation__date=day).select_related('operation').order_by('pk')
    return render(request,'finance/day.html',{'account':account,'date':day,'page':Paginator(rows,50).get_page(request.GET.get('page'))})
