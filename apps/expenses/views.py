from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from .models import Expense, ChartOfAccount, ClassificationRule
from . import forms, services, selectors


def check_read(user):
    if not(user.has_perm('core.operate_expenses') or user.has_perm('core.view_expense_reports')):raise PermissionDenied


def form_error(form,exc):
    form.add_error(None,'; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Registro duplicado ou inconsistente; reabra para conferir.')


@login_required
def expense_list(request):
    check_read(request.user);form=forms.FilterForm(request.GET or {'status':'active'})
    rows=selectors.expenses(form.cleaned_data) if form.is_valid() else Expense.objects.none()
    return render(request,'expenses/list.html',{'form':form,'page':Paginator(rows,30).get_page(request.GET.get('page'))})


@login_required
@permission_required('core.operate_expenses',raise_exception=True)
def expense_new(request):
    form=forms.ExpenseForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        data=dict(form.cleaned_data);key=data.pop('key')
        try:
            obj=services.create_expense(actor=request.user,key=key,data=data)
            messages.success(request,'Despesa registrada por competência. O pagamento continua separado no financeiro.')
            return redirect('expense_detail',pk=obj.pk)
        except (ValidationError,IntegrityError) as exc:form_error(form,exc)
    return render(request,'expenses/form.html',{'title':'Nova despesa','form':form,'button':'Registrar despesa','help':'Informe a competência do serviço/consumo. Compra de estoque, principal de dívida e abertura não são despesas. Categoria em branco aplica regras; sem correspondência, fica a classificar.'})


@login_required
def expense_detail(request,pk):
    check_read(request.user)
    obj=get_object_or_404(Expense.objects.select_related('title','category','supplier','recurrence_of'),pk=pk)
    return render(request,'expenses/detail.html',{'expense':obj,'reclassify':forms.ReclassifyForm(initial={'category':obj.category_id,'cost_center':obj.cost_center,'revision':obj.revision}),'cancel':forms.CancelForm(),'history':Paginator(obj.revisions.select_related('actor').order_by('-number'),20).get_page(request.GET.get('page'))})


@login_required
@permission_required('core.operate_expenses',raise_exception=True)
@require_POST
def expense_action(request,pk,action):
    get_object_or_404(Expense,pk=pk)
    form=(forms.ReclassifyForm if action=='classify' else forms.CancelForm)(request.POST)
    if action=='stop':
        try:
            services.stop_recurrence(actor=request.user,pk=pk)
            messages.success(request,'Novas ocorrências desabilitadas. As existentes foram preservadas.')
        except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
        return redirect('expense_detail',pk=pk)
    if form.is_valid():
        try:
            if action=='classify':services.reclassify(actor=request.user,pk=pk,**form.cleaned_data)
            else:services.cancel_expense(actor=request.user,pk=pk,**form.cleaned_data)
            messages.success(request,'Alteração registrada com histórico.');return redirect('expense_detail',pk=pk)
        except (ValidationError,IntegrityError) as exc:form_error(form,exc)
    return render(request,'expenses/form.html',{'title':'Revisar despesa','form':form,'button':'Confirmar'},status=400)


@login_required
@permission_required('core.manage_expense_rules',raise_exception=True)
def configuration_list(request):
    return render(request,'expenses/configuration.html',{'categories':Paginator(ChartOfAccount.objects.select_related('parent'),40).get_page(request.GET.get('categories_page')),'rules':Paginator(ClassificationRule.objects.select_related('category'),30).get_page(request.GET.get('rules_page'))})


@login_required
@permission_required('core.manage_expense_rules',raise_exception=True)
def configuration_edit(request,kind,pk=None):
    model,formclass,service=(ChartOfAccount,forms.CategoryForm,services.save_category) if kind=='category' else (ClassificationRule,forms.RuleForm,services.save_rule)
    obj=get_object_or_404(model,pk=pk) if pk else None
    form=formclass(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        try:
            service(actor=request.user,data=form.cleaned_data,pk=pk)
            messages.success(request,'Configuração salva. Despesas anteriores foram preservadas.')
            return redirect('expense_configuration')
        except (ValidationError,IntegrityError) as exc:form_error(form,exc)
    return render(request,'expenses/form.html',{'title':'Categoria do plano de contas' if kind=='category' else 'Regra de classificação','form':form,'button':'Salvar configuração','help':'Códigos: 04, 04.01, 04.01.01. Categorias agrupadoras não recebem lançamentos. Regras seguem prioridade crescente e, em empate, ordem de cadastro; seleção manual prevalece.'})


@login_required
@permission_required('core.view_expense_reports',raise_exception=True)
def report(request):
    form=forms.FilterForm(request.GET or {'period':'month','status':'active'});groups=[];totals={}
    if form.is_valid():groups,totals=selectors.expense_report(form.cleaned_data)
    return render(request,'expenses/report.html',{'form':form,'groups':groups,'totals':totals})


@login_required
@permission_required('core.view_expense_reports',raise_exception=True)
def report_api(request):
    form=forms.FilterForm(request.GET)
    if not form.is_valid():return JsonResponse({'errors':form.errors.get_json_data()},status=400)
    groups,totals=selectors.expense_report(form.cleaned_data)
    return JsonResponse({'categories':[{**r,'amount':str(r['amount'])} for r in groups],'totals':{k:str(v) for k,v in totals.items()}})


@login_required
@permission_required('core.operate_expenses',raise_exception=True)
def recurrence(request,pk):
    obj=get_object_or_404(Expense.objects.select_related('title','category','supplier'),pk=pk)
    form=forms.RecurrenceForm(request.POST or None);rows=[]
    if request.method=='POST' and form.is_valid():
        try:
            if request.POST.get('action')=='confirm':
                created=services.generate_recurrence(actor=request.user,pk=pk,months=form.cleaned_data['months'],preview_hash=form.cleaned_data['preview_hash'])
                messages.success(request,f'{len(created)} despesas geradas. Ocorrências existentes não foram duplicadas.')
                return redirect('expense_detail',pk=pk)
            rows,hash_value=services.recurrence_preview(obj,form.cleaned_data['months'])
            form=forms.RecurrenceForm(initial={'months':form.cleaned_data['months'],'preview_hash':hash_value})
        except (ValidationError,IntegrityError) as exc:form_error(form,exc)
    return render(request,'expenses/recurrence.html',{'expense':obj,'form':form,'rows':rows})
