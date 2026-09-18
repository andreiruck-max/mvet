from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from .models import Sale, SalesChannel, TaxRule
from .forms import SaleForm, Items, CancelForm, ChannelForm, TaxForm, FilterForm, ExtraCosts, TaxChangeForm
from .services import save_draft, confirm, cancel, save_configuration, EDIT_FIELDS
from .selectors import sales
from .taxes import change_rate, effective_terms
from apps.core.services import require

def check_read(user):
    if not user.has_perm('core.view_sales'):raise PermissionDenied

@login_required
def sale_list(request):
    check_read(request.user)
    form=FilterForm(request.GET)
    rows=sales(form.cleaned_data) if form.is_valid() else Sale.objects.none()
    return render(request,'sales/list.html',{'form':form,'page':Paginator(rows,30).get_page(request.GET.get('page'))})

@login_required
@permission_required('core.operate_sales',raise_exception=True)
def sale_edit(request,pk=None):
    obj=get_object_or_404(Sale,pk=pk) if pk else None
    if obj and obj.status!='DRAFT':
        messages.error(request,'Somente rascunhos podem ser editados.');return redirect('sale_detail',pk=pk)
    form=SaleForm(request.POST or None,instance=obj)
    initial=[{'product':i.product_id,'quantity':i.quantity} for i in obj.items.all()] if obj else []
    formset=Items(request.POST or None,initial=initial)
    extra_initial=list(obj.extra_costs.values('name','amount')) if obj else []
    extra_formset=ExtraCosts(request.POST or None,initial=extra_initial,prefix='extras')
    if request.method=='POST':
        valid=form.is_valid();items_valid=formset.is_valid();extras_valid=extra_formset.is_valid()
        if valid and items_valid and extras_valid:
            try:
                items=[(f.cleaned_data['product'].pk,f.cleaned_data['quantity']) for f in formset if f.cleaned_data and not f.cleaned_data.get('DELETE')]
                extras=[(f.cleaned_data['name'],f.cleaned_data['amount']) for f in extra_formset if f.cleaned_data and not f.cleaned_data.get('DELETE')]
                sale=save_draft(actor=request.user,key=form.cleaned_data['key'],data={k:form.cleaned_data[k] for k in EDIT_FIELDS},items=items,sale_id=pk,revision=form.cleaned_data['revision'],extra_costs=extras)
                messages.success(request,'Rascunho salvo. Revise e confirme para baixar o estoque.')
                return redirect('sale_detail',pk=sale.pk)
            except ValidationError as exc:form.add_error(None,'; '.join(exc.messages))
            except IntegrityError:form.add_error(None,'NF e série já utilizadas. Verifique as vendas cadastradas.')
    labels={str(i.product_id):str(i.product) for i in obj.items.select_related('product')} if obj else {}
    return render(request,'sales/edit.html',{'form':form,'formset':formset,'extra_formset':extra_formset,'labels':labels,'sale':obj})

@login_required
def sale_detail(request,pk):
    check_read(request.user)
    sale=get_object_or_404(Sale.objects.select_related('channel','location','created_by','confirmed_by','cancelled_by'),pk=pk)
    return render(request,'sales/detail.html',{'sale':sale,'items':sale.items.select_related('product'),'cancel_form':CancelForm(),'extra_costs':sale.extra_costs.all(),'tax_revisions':sale.tax_revisions.select_related('change__actor')})

@login_required
@permission_required('core.operate_sales',raise_exception=True)
@require_POST
def sale_confirm(request,pk):
    get_object_or_404(Sale,pk=pk)
    try:
        revision=int(request.POST.get('revision','-1'))
        confirm(actor=request.user,sale_id=pk,revision=revision)
        messages.success(request,'Venda confirmada. Estoque atualizado.')
    except (ValidationError,ValueError) as exc:messages.error(request,'; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Revisão inválida.')
    return redirect('sale_detail',pk=pk)

@login_required
@permission_required('core.operate_sales',raise_exception=True)
@require_POST
def sale_cancel(request,pk):
    get_object_or_404(Sale,pk=pk);form=CancelForm(request.POST)
    if form.is_valid():
        try:
            cancel(actor=request.user,sale_id=pk,reason=form.cleaned_data['reason']);messages.success(request,'Venda cancelada. Movimentos preservados e estoque reposto, quando aplicável.')
        except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
    else:messages.error(request,'Informe o motivo do cancelamento.')
    return redirect('sale_detail',pk=pk)

@login_required
@permission_required('core.view_margins',raise_exception=True)
def sale_result(request,pk):
    sale=get_object_or_404(Sale,pk=pk)
    if sale.status=='DRAFT':return JsonResponse({'status':sale.status,'detail':'Custo calculado na confirmação.'})
    result={'status':sale.status,'revenue':str(sale.revenue),'contribution':str(sale.contribution),'margin_percent':str(sale.margin_percent) if sale.margin_percent is not None else None}
    if request.user.has_perm('core.view_costs'):result['cmv']=str(sale.cmv)
    return JsonResponse(result)

@login_required
def configuration(request,kind,pk=None):
    require(request.user,'core.manage_channels' if kind == 'canais' else 'core.manage_taxes')
    choices={'canais':(SalesChannel,ChannelForm,'Canais de venda'),'impostos':(TaxRule,TaxForm,'Regras tributárias')}
    if kind not in choices:raise PermissionDenied
    model,form_class,title=choices[kind]
    obj=get_object_or_404(model,pk=pk) if pk else None
    form=form_class(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        try:
            save_configuration(actor=request.user,model=model,data=form.cleaned_data,pk=pk)
            return redirect('sales_configuration',kind=kind)
        except ValidationError as exc:form.add_error(None,'; '.join(exc.messages))
        except IntegrityError:form.add_error(None,'Cadastro duplicado.')
    return render(request,'sales/configuration.html',{'form':form,'kind':kind,'title':title,'page':Paginator(model.objects.all(),30).get_page(request.GET.get('page'))})


@login_required
@permission_required('core.manage_taxes',raise_exception=True)
def tax_change(request,pk):
    from django.utils import timezone
    rule=get_object_or_404(TaxRule,pk=pk)
    rate,base,_=effective_terms(rule,timezone.localdate())
    latest=rule.changes.order_by('-pk').first()
    form=TaxChangeForm(request.POST or None,initial={'rate':rate,'base':base,'revision':latest.pk if latest else 0})
    if request.method=='POST' and form.is_valid():
        try:
            change,count=change_rate(actor=request.user,rule_id=pk,**form.cleaned_data)
            messages.success(request,f'Alíquota registrada. {count} venda(s) recalculada(s).')
            return redirect('tax_change',pk=pk)
        except ValidationError as exc:form.add_error(None,'; '.join(exc.messages))
    return render(request,'sales/tax_change.html',{'form':form,'rule':rule,'rate':rate,'changes':rule.changes.select_related('actor')})
