from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.core import signing
from django.utils import timezone
from uuid import uuid4
from decimal import Decimal
from datetime import date
from apps.accounts.access import master
from . import editing, bulk
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
    return render(request,'expenses/list.html',{'can_bulk':all(request.user.has_perm(p) for p in ['core.operate_expenses','core.operate_finance','core.pay_titles']),'form':form,'summary':selectors.expense_summary(rows) if request.user.has_perm('core.view_expense_reports') else None,'page':Paginator(rows,30).get_page(request.GET.get('page'))})


@login_required
@permission_required('core.operate_expenses',raise_exception=True)
def expense_new(request):
    form=forms.ExpenseForm(request.POST or None)
    category=request.GET.get('category','')
    if request.method=='GET' and category.isascii() and category.isdecimal() and len(category)<18:
        if form.fields['category'].queryset.filter(pk=int(category)).exists():form.initial['category']=int(category)
    if request.method=='POST' and form.is_valid():
        data=dict(form.cleaned_data);key=data.pop('key')
        try:
            obj=services.create_expense(actor=request.user,key=key,data=data)
            messages.success(request,'Despesa registrada por competência. O pagamento continua separado no financeiro.')
            return redirect('expense_detail',pk=obj.pk)
        except (ValidationError,IntegrityError) as exc:form_error(form,exc)
    return render(request,'expenses/form.html',{'title':'Nova despesa','form':form,'expense_form':True,'button':'Registrar despesa','help':'Registre a competência e o vencimento; o pagamento é feito no financeiro. Fornecedor e favorecido são opcionais. Compra de estoque, principal de dívida e abertura não são despesas.'})


@login_required
def expense_detail(request,pk):
    check_read(request.user)
    obj=get_object_or_404(Expense.objects.select_related('title','category','supplier','recurrence_of'),pk=pk)
    history=Paginator(obj.revisions.select_related('actor').order_by('-number'),20).get_page(request.GET.get('page'))
    for entry in history:
        entry.changes=revision_changes(entry)
    return render(request,'expenses/detail.html',{'expense':obj,'reclassify':forms.ReclassifyForm(initial={'category':obj.category_id,'cost_center':obj.cost_center,'revision':obj.revision}),'cancel':forms.CancelForm(),'history':history})


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


@login_required
def expense_edit(request,pk):
    master(request.user)
    obj=get_object_or_404(Expense.objects.select_related('title'),pk=pk)
    form=forms.ExpenseEditForm(request.POST if request.method=='POST' else None,instance=obj)
    if request.method=='POST' and form.is_valid():
        data=dict(form.cleaned_data)
        revision=data.pop('revision');title_revision=data.pop('title_revision');reason=data.pop('reason')
        try:
            editing.edit_expense(actor=request.user,pk=pk,revision=revision,title_revision=title_revision,reason=reason,data=data)
            messages.success(request,'Despesa atualizada com histórico. Pagamentos existentes foram preservados.')
            return redirect('expense_detail',pk=pk)
        except (ValidationError,IntegrityError) as exc:form_error(form,exc)
    return render(request,'expenses/form.html',{'title':'Editar despesa','form':form,'expense_form':True,'button':'Salvar alterações',
        'help':'A edição altera esta despesa e sua obrigação. Pagamentos já realizados permanecem no histórico; o valor não pode ser menor que o principal liquidado. Alterar a conta prevista não transfere pagamentos anteriores. Ocorrências já geradas não são alteradas.'},status=400 if request.method=='POST' else 200)


def revision_changes(entry):
    labels={'description':'Descrição','amount':'Valor','document_date':'Documento','competence':'Competência',
        'supplier_id':'Fornecedor (ID)','counterparty':'Favorecido','category_snapshot':'Categoria',
        'cost_center':'Centro de custo','notes':'Observação','recurrence_enabled':'Recorrência',
        'due_date':'Vencimento','account_id':'Conta prevista (ID)'}
    result=[]
    for section in ['expense','title'] if 'expense' in entry.before else [None]:
        before=entry.before.get(section) or {} if section else entry.before
        after=entry.after.get(section) or {} if section else entry.after
        for field,label in labels.items():
            if section=='title' and field not in ['due_date','account_id']:continue
            if before.get(field)==after.get(field):continue
            def display(value):
                if field=='category_snapshot':return ' / '.join(n['code']+' '+n['name'] for n in (value or {}).get('path',[])) or 'A classificar'
                if isinstance(value,bool):return 'Sim' if value else 'Não'
                if field in ['document_date','competence','due_date'] and value:return date.fromisoformat(value).strftime('%d/%m/%Y')
                if field=='amount' and value:return 'R$ '+format(Decimal(value),',.2f').replace(',','_').replace('.',',').replace('_','.')
                return value if value is not None and value!='' else '—'
            result.append((label,display(before.get(field)),display(after.get(field))))
    return result


@login_required
@require_POST
def expense_bulk_payment(request):
    bulk.check_access(request.user)
    if request.POST.get('action')=='confirm':
        try:
            payload=signing.loads(request.POST.get('preview',''),salt='expenses.bulk',max_age=1800)
            if payload['actor']!=request.user.pk:raise signing.BadSignature()
            operations=bulk.settle_batch(actor=request.user,key=payload['key'],rows=payload['rows'],
                account_id=payload['account'],date=date.fromisoformat(payload['date']))
            messages.success(request,f'{len(operations)} despesas baixadas na conta e data selecionadas. Categorias preservadas.')
            return redirect('expenses')
        except signing.BadSignature:
            error='Conferência inválida ou expirada. Selecione as despesas novamente.'
        except (ValidationError,IntegrityError) as exc:
            error='; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Não foi possível concluir o lote. Nenhuma baixa nova foi gravada; confira novamente.'
        return render(request,'expenses/bulk.html',{'error':error},status=400)
    form=forms.BulkPaymentForm(request.POST if request.POST.get('action')=='review' else None)
    try:
        raw_ids=request.POST.getlist('expense_ids')
        if len(raw_ids)>100 or any(not pk.isascii() or not pk.isdecimal() or len(pk)>18 for pk in raw_ids):
            raise ValidationError('Seleção inválida: use até 100 despesas.')
        ids=[int(pk) for pk in raw_ids]
        rows=bulk.selection(ids)
    except (ValueError,ValidationError) as exc:
        return render(request,'expenses/bulk.html',{'error':'; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Seleção inválida.'},status=400)
    token=None
    if request.POST.get('action')=='review' and form.is_valid():
        # Validate dates without writing; authoritative checks run again at confirmation.
        from apps.core.models import Company
        selected_date=form.cleaned_data['date'];account=form.cleaned_data['account']
        if selected_date<max(Company.objects.get(pk=1).cutover_date,account.opening_date,max(obj.document_date for obj in rows)):
            form.add_error('date','Data anterior ao corte, à abertura da conta ou ao documento de uma despesa.')
        else:
            token=signing.dumps({'actor':request.user.pk,'key':str(uuid4()),'rows':bulk.preview_rows(rows),
                                'account':account.pk,'date':selected_date.isoformat()},salt='expenses.bulk')
    return render(request,'expenses/bulk.html',{'form':form,'rows':rows,'total':sum((obj.title.remaining for obj in rows),Decimal(0)),
        'preview':token,'future':form.is_bound and form.is_valid() and form.cleaned_data['date']>timezone.localdate()})
