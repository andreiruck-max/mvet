from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from .models import Supplier, Purchase
from .forms import SupplierForm, PurchaseForm, Items, Installments, ReceiveForm, CancelForm, FilterForm
from .services import save_supplier, save_draft, confirm, receive, cancel, FIELDS
from .selectors import purchases, supplier_report

def check_read(user):
    if not user.has_perm('core.operate_purchases') and not user.has_perm('core.view_purchase_reports'):raise PermissionDenied

@login_required
def purchase_list(request):
    check_read(request.user);form=FilterForm(request.GET)
    rows=purchases(form.cleaned_data) if form.is_valid() else Purchase.objects.none()
    return render(request,'purchases/list.html',{'form':form,'page':Paginator(rows,30).get_page(request.GET.get('page'))})

@login_required
def supplier_list(request):
    check_read(request.user);rows=Supplier.objects.all();q=request.GET.get('q','').strip()
    if q:rows=rows.filter(Q(legal_name__icontains=q)|Q(trade_name__icontains=q)|Q(document__icontains=q))
    status=request.GET.get('status','active')
    if status in {'active','inactive'}:rows=rows.filter(active=status=='active')
    return render(request,'purchases/suppliers.html',{'page':Paginator(rows,30).get_page(request.GET.get('page'))})

@login_required
@permission_required('core.operate_purchases',raise_exception=True)
def supplier_edit(request,pk=None):
    obj=get_object_or_404(Supplier,pk=pk) if pk else None;form=SupplierForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        try:
            obj=save_supplier(actor=request.user,data=form.cleaned_data,pk=pk);return redirect('supplier_detail',pk=obj.pk)
        except ValidationError as exc:form.add_error(None,'; '.join(exc.messages))
        except IntegrityError:form.add_error(None,'CPF/CNPJ já cadastrado.')
    return render(request,'purchases/supplier_edit.html',{'form':form,'supplier':obj})

@login_required
def supplier_detail(request,pk):
    check_read(request.user);supplier=get_object_or_404(Supplier,pk=pk);context={'supplier':supplier}
    if request.user.has_perm('core.view_purchase_reports'):
        summary,prices,outstanding=supplier_report(supplier)
        context.update(summary=summary,prices=Paginator(prices,20).get_page(request.GET.get('prices_page')),outstanding=Paginator(outstanding,20).get_page(request.GET.get('due_page')))
    return render(request,'purchases/supplier.html',context)

@login_required
@permission_required('core.view_purchase_reports',raise_exception=True)
def supplier_summary(request,pk):
    supplier=get_object_or_404(Supplier,pk=pk);summary,_,_=supplier_report(supplier)
    return JsonResponse({k:str(v) if v is not None else None for k,v in summary.items()})

@login_required
@permission_required('core.operate_purchases',raise_exception=True)
def purchase_edit(request,pk=None):
    obj=get_object_or_404(Purchase,pk=pk) if pk else None
    if obj and obj.status!='DRAFT':messages.error(request,'Somente rascunhos podem ser editados.');return redirect('purchase_detail',pk=pk)
    form=PurchaseForm(request.POST or None,instance=obj)
    initial=[{'product':i.product_id,'quantity':i.quantity,'unit_cost':i.unit_cost} for i in obj.items.all()] if obj else []
    schedule=list(obj.installments.values('due_date','amount','notes')) if obj else []
    items=Items(request.POST or None,initial=initial);installments=Installments(request.POST or None,initial=schedule,prefix='installments')
    if request.method=='POST':
        valid=form.is_valid();items_valid=items.is_valid();schedule_valid=installments.is_valid()
        if valid and items_valid and schedule_valid:
            try:
                lines=[(f.cleaned_data['product'].pk,f.cleaned_data['quantity'],f.cleaned_data['unit_cost']) for f in items if f.cleaned_data and not f.cleaned_data.get('DELETE')]
                dates=[(f.cleaned_data['due_date'],f.cleaned_data['amount'],f.cleaned_data['notes']) for f in installments if f.cleaned_data and not f.cleaned_data.get('DELETE')]
                p=save_draft(actor=request.user,key=form.cleaned_data['key'],data={k:form.cleaned_data[k] for k in FIELDS},items=lines,installments=dates,purchase_id=pk,revision=form.cleaned_data['revision'])
                messages.success(request,'Rascunho salvo. Confira o total, o rateio e as parcelas.');return redirect('purchase_detail',pk=p.pk)
            except ValidationError as exc:form.add_error(None,'; '.join(exc.messages))
            except IntegrityError:form.add_error(None,'Documento e série já utilizados para este fornecedor.')
    labels={str(i.product_id):str(i.product) for i in obj.items.select_related('product')} if obj else {}
    return render(request,'purchases/edit.html',{'form':form,'formset':items,'installments':installments,'labels':labels,'purchase':obj})

@login_required
def purchase_detail(request,pk):
    check_read(request.user);p=get_object_or_404(Purchase.objects.select_related('supplier','location','created_by','received_by','cancelled_by'),pk=pk)
    return render(request,'purchases/detail.html',{'purchase':p,'items':p.items.all(),'installments':p.installments.all(),'receive_form':ReceiveForm(initial={'revision':p.revision}),'cancel_form':CancelForm()})

@login_required
@permission_required('core.operate_purchases',raise_exception=True)
@require_POST
def purchase_confirm(request,pk):
    get_object_or_404(Purchase,pk=pk)
    try:
        confirm(actor=request.user,purchase_id=pk,revision=int(request.POST.get('revision','-1')));messages.success(request,'Compra confirmada. Parcelas registradas; estoque aguarda recebimento.')
    except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
    except ValueError:messages.error(request,'Revisão inválida.')
    return redirect('purchase_detail',pk=pk)

@login_required
@permission_required('core.operate_purchases',raise_exception=True)
@require_POST
def purchase_receive(request,pk):
    get_object_or_404(Purchase,pk=pk);form=ReceiveForm(request.POST)
    if form.is_valid():
        try:
            receive(actor=request.user,purchase_id=pk,**form.cleaned_data);messages.success(request,'Compra recebida. Estoque e custo médio atualizados.')
        except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
    else:messages.error(request,'Informe data de recebimento e revisão válidas.')
    return redirect('purchase_detail',pk=pk)

@login_required
@permission_required('core.operate_purchases',raise_exception=True)
@require_POST
def purchase_cancel(request,pk):
    get_object_or_404(Purchase,pk=pk);form=CancelForm(request.POST)
    if form.is_valid():
        try:
            cancel(actor=request.user,purchase_id=pk,reason=form.cleaned_data['reason']);messages.success(request,'Compra cancelada. Parcelas canceladas e recebimento revertido, quando aplicável.')
        except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
    else:messages.error(request,'Informe o motivo do cancelamento.')
    return redirect('purchase_detail',pk=pk)
