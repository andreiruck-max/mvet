from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from apps.core.services import audit, require
from apps.products.models import Product, Brand, ProductCategory
from apps.products.services import save_product, remove_product, set_components
from .models import StockLocation, StockOperation, StockMovement, StockBalance
from .forms import ProductForm, OperationForm, NamedForm, ReversalForm, Components
from .selectors import catalog, kit_summary
from .services import execute, reverse, domain_lock

def can_read(user):
    return user.is_active and user.has_perm('core.view_stock')

def check_read(user):
    if not can_read(user):raise PermissionDenied

@login_required
def products(request):
    check_read(request.user)
    page=Paginator(catalog(request.GET),30).get_page(request.GET.get('page'))
    return render(request,'inventory/products.html',{'page':page})

@login_required
def lookup(request):
    check_read(request.user)
    query=request.GET.get('q','').strip()
    if not query:return JsonResponse({'results':[]})
    rows=Product.objects.filter(active=True).filter(Q(sku__icontains=query)|Q(name__icontains=query)).order_by('name')[:20]
    location=request.GET.get('location')
    if location and not location.isdecimal():return JsonResponse({'results':[]},status=400)
    results=[]
    for p in rows:
        item={'id':p.pk,'label':str(p),'quantity':str(p.quantity),'kind':p.kind}
        if p.kind=='KIT':
            _,qty,cost=kit_summary(p);item['quantity']=str(qty)
        else:cost=p.average_cost
        if location:
            if p.kind=='KIT':
                parts=list(p.components.select_related('component'))
                balances={b.product_id:b.quantity for b in StockBalance.objects.filter(location_id=location,product_id__in=[part.component_id for part in parts])}
                item['quantity']=str(min((balances.get(part.component_id,Decimal('0'))//part.quantity for part in parts),default=0))
            else:item['quantity']=str(p.balances.filter(location_id=location).values_list('quantity',flat=True).first() or 0)
        if request.user.has_perm('core.view_costs'):item['cost']=str(cost)
        results.append(item)
    return JsonResponse({'results':results})

@login_required
def product_detail(request,pk):
    check_read(request.user);p=get_object_or_404(Product,pk=pk)
    parts,available,cost=kit_summary(p)
    moves=Paginator(p.movements.select_related('operation','location').order_by('-pk'),25).get_page(request.GET.get('page'))
    return render(request,'inventory/product.html',{'product':p,'parts':parts,'available':available,'kit_cost':cost,'page':moves,'balances':p.balances.select_related('location')})

@login_required
@permission_required('core.operate_stock',raise_exception=True)
def product_edit(request,pk=None):
    obj=get_object_or_404(Product,pk=pk) if pk else None
    form=ProductForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        try:
            product=save_product(actor=request.user,pk=pk,data=form.cleaned_data)
            messages.success(request,'Produto salvo.');return redirect('product_detail',pk=product.pk)
        except ValidationError as error:form.add_error(None,error)
        except IntegrityError:form.add_error(None,'SKU já utilizado. Atualize a página.')
    return render(request,'inventory/form.html',{'form':form,'title':'Editar produto' if pk else 'Novo produto'})

@login_required
@permission_required('core.operate_stock',raise_exception=True)
@require_POST
def product_remove(request,pk):
    messages.success(request,remove_product(actor=request.user,pk=pk));return redirect('products')

@login_required
@permission_required('core.operate_stock',raise_exception=True)
def components(request,pk):
    p=get_object_or_404(Product,pk=pk,kind='KIT')
    initial=[{'component':i.component_id,'quantity':i.quantity} for i in p.components.all()]
    formset=Components(request.POST or None,initial=initial)
    error=None
    if request.method=='POST' and formset.is_valid():
        items=[(f.cleaned_data['component'].pk,f.cleaned_data['quantity']) for f in formset if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        try:
            set_components(actor=request.user,kit_id=pk,items=items);return redirect('product_detail',pk=pk)
        except ValidationError as exc:error='; '.join(exc.messages)
    labels={str(i.component_id):str(i.component) for i in p.components.select_related('component')}
    return render(request,'inventory/components.html',{'product':p,'formset':formset,'error':error,'labels':labels})

@login_required
@permission_required('core.operate_stock',raise_exception=True)
def operation_new(request):
    form=OperationForm(request.POST or None,actor=request.user)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data
        try:
            op=execute(actor=request.user,key=d['key'],kind=d['kind'],date=d['date'],reason=d['reason'],product_id=d['product'].pk,location_id=d['location'].pk,quantity=Decimal(d['quantity']),cost=d.get('cost'),target_location_id=d['target_location'].pk if d.get('target_location') else None,target_product_id=d['target_product'].pk if d.get('target_product') else None,target_quantity=d.get('target_quantity'))
            messages.success(request,'Movimento confirmado.');return redirect('operation_detail',pk=op.pk)
        except ValidationError as exc:form.add_error(None,"; ".join(exc.messages))
    return render(request,'inventory/form.html',{'form':form,'title':'Movimentar estoque','operation':True})

@login_required
@permission_required('core.operate_stock',raise_exception=True)
def operations(request):
    rows=StockOperation.objects.select_related('actor')
    q=request.GET.get('q','').strip()
    if q: rows=rows.filter(Q(reason__icontains=q)|Q(movements__product__sku__icontains=q)|Q(movements__product__name__icontains=q)).distinct()
    from django.forms import DateField
    for field,lookup_name in [('start','date__gte'),('end','date__lte')]:
        try:
            if request.GET.get(field):rows=rows.filter(**{lookup_name:DateField().clean(request.GET[field])})
        except ValidationError:messages.error(request,'Filtro de data inválido.')
    return render(request,'inventory/operations.html',{'page':Paginator(rows,30).get_page(request.GET.get('page'))})

@login_required
@permission_required('core.operate_stock',raise_exception=True)
def operation_detail(request,pk):
    op=get_object_or_404(StockOperation,pk=pk)
    form=ReversalForm(request.POST or None)
    if request.method=='POST':
        if not request.user.has_perm('core.view_costs'):raise PermissionDenied
        if form.is_valid():
            try:
                new=reverse(actor=request.user,operation_id=pk,**form.cleaned_data)
                messages.success(request,'Estorno registrado.');return redirect('operation_detail',pk=new.pk)
            except ValidationError as exc:form.add_error(None,"; ".join(exc.messages))
    return render(request,'inventory/operation.html',{'operation':op,'movements':op.movements.select_related('product','location'),'form':form})

NAMED={'locais':(StockLocation,'Locais de estoque'),'marcas':(Brand,'Marcas'),'categorias':(ProductCategory,'Categorias')}
@login_required
@permission_required('core.operate_stock',raise_exception=True)
def named(request,kind,pk=None):
    require(request.user,'core.manage_stock_catalogs')
    if kind not in NAMED:raise PermissionDenied
    model,title=NAMED[kind];obj=get_object_or_404(model,pk=pk) if pk else None
    form=NamedForm(request.POST or None,initial={'name':obj.name,'active':obj.active} if obj else None)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                domain_lock()
                obj=model.objects.select_for_update().get(pk=pk) if pk else model()
                before={'name':obj.name,'active':obj.active}
                from apps.core.models import Company
                if model is StockLocation and pk and not form.cleaned_data['active'] and Company.objects.filter(default_stock_location_id=pk).exists():
                    raise ValidationError('Selecione outro estoque padrão nas configurações antes de inativar este estoque.')
                for k,v in form.cleaned_data.items():setattr(obj,k,v)
                obj.full_clean();obj.save();audit(request.user,obj,'save_catalog',before,form.cleaned_data)
            return redirect('named',kind=kind)
        except ValidationError as exc:form.add_error(None,'; '.join(exc.messages))
        except IntegrityError:form.add_error(None,'Nome já utilizado.')
    return render(request,'inventory/named.html',{'title':title,'kind':kind,'form':form,'page':Paginator(model.objects.all(),30).get_page(request.GET.get('page'))})
