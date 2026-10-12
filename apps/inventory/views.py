from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse as url_reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from apps.core.services import audit, require
from apps.core.navigation import return_url, detail_url
from apps.products.models import Product, Brand, ProductCategory
from apps.products.services import save_product, remove_product, set_components, inactivate_product
from .models import StockLocation, StockOperation, StockMovement, StockBalance
from .forms import ProductForm, OperationForm, NamedForm, ReversalForm, Components
from .selectors import catalog, kit_summary, selected_location, location_values, stock_totals, search_products
from .services import execute, reverse, domain_lock
from apps.products.pricing import sale_price, retail_location
from apps.core.models import Company

def can_read(user):
    return user.is_active and user.has_perm('core.view_stock')

def check_read(user):
    if not can_read(user):raise PermissionDenied

@login_required
def planning(request):
    check_read(request.user)
    if not (request.user.has_perm('core.operate_purchases') or request.user.has_perm('core.view_purchase_reports')):
        raise PermissionDenied
    from .planning import PlanningForm, purchase_plan
    location, _ = selected_location({})
    defaults = {'zero_days': 30, 'history_days': 30, 'coverage_days': 30,
                'location': location.pk if location else None}
    defaults.update(request.session.get('purchase_plan_filters', {}))
    data = dict(defaults, **request.GET.dict())
    form = PlanningForm(data)
    rows = []; totals = {}
    if form.is_valid():
        values = form.cleaned_data
        request.session['purchase_plan_filters'] = {name: values[name] for name in ('zero_days', 'history_days', 'coverage_days')}
        request.session['purchase_plan_filters']['location'] = values['location'].pk
        rows, totals = purchase_plan(**values)
    page = Paginator(rows, 50).get_page(request.GET.get('page'))
    return render(request, 'inventory/planning.html', {'form': form, 'page': page, 'totals': totals})

@login_required
def products(request):
    check_read(request.user)
    try:
        location, locations = selected_location(request.GET)
    except ValidationError as exc:
        return HttpResponseBadRequest('; '.join(exc.messages))
    page = Paginator(catalog(request.GET, location).prefetch_related('balances'), 50).get_page(request.GET.get('page'))
    default_markup = Company.objects.get(pk=1).default_markup
    for product in page:
        product.sale_price = sale_price(product, product.stock_cost, default_markup) if product.kind == 'SIMPLE' else None
    context = {'page': page, 'location': location, 'locations': locations, 'show_prices': location is not None and location == retail_location()}
    if request.user.has_perm('core.view_costs'):
        for product in page:
            product.stock_value = location_values(product).get(location.pk if location else None, Decimal(0))
        context['stock_totals'], context['stock_total'] = stock_totals(locations)
        context['stock_totals'].sort(key=lambda row: (-row['value'], row['location'].name))
    return render(request, 'inventory/products.html', context)

@login_required
def lookup(request):
    check_read(request.user)
    query=request.GET.get('q','').strip()
    if not query:return JsonResponse({'results':[]})
    rows=search_products(Product.objects.filter(active=True), query).order_by('name')[:20]
    location=request.GET.get('location')
    if location and not location.isdecimal():return JsonResponse({'results':[]},status=400)
    default_markup = Company.objects.get(pk=1).default_markup
    retail = retail_location()
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
                local_costs = {b.product_id: b.average_cost for b in StockBalance.objects.filter(location_id=location, product_id__in=[part.component_id for part in parts])}
                cost = sum((local_costs.get(part.component_id, Decimal(0)) * part.quantity for part in parts), Decimal(0))
            else:
                balance = p.balances.filter(location_id=location).first()
                item['quantity'] = str(balance.quantity if balance else 0)
                cost = balance.average_cost if balance else Decimal(0)
        if retail and (not location or str(retail.pk) == location):
            if p.kind == 'KIT':
                retail_costs = {b.product_id: b.average_cost for b in StockBalance.objects.filter(location=retail)}
                price_cost = sum((retail_costs.get(part.component_id, Decimal(0)) * part.quantity for part in p.components.all()), Decimal(0))
            else:
                retail_balance = p.balances.filter(location=retail).first()
                price_cost = retail_balance.average_cost if retail_balance else Decimal(0)
            item['sale_price'] = str(sale_price(p, price_cost, default_markup))
        if request.user.has_perm('core.view_costs'):item['cost']=str(cost)
        results.append(item)
    return JsonResponse({'results':results})

@login_required
def product_detail(request,pk):
    check_read(request.user);p=get_object_or_404(Product,pk=pk)
    parts,available,cost=kit_summary(p)
    moves=Paginator(p.movements.select_related('operation','location').order_by('-pk'),25).get_page(request.GET.get('page'))
    balances = list(p.balances.select_related('location'))
    default_markup = Company.objects.get(pk=1).default_markup
    retail = retail_location()
    for balance in balances:
        balance.show_price = retail is not None and balance.location_id == retail.pk
        balance.sale_price = sale_price(p, balance.average_cost, default_markup)
    p.sale_price = None
    if p.kind == 'KIT' and retail:
        retail_costs = {b.product_id: b.average_cost for b in StockBalance.objects.filter(location=retail)}
        p.sale_price = sale_price(p, sum((retail_costs.get(part.component_id, Decimal(0)) * part.quantity for part in parts), Decimal(0)), default_markup)
    return render(request,'inventory/product.html',{'product':p,'parts':parts,'available':available,'kit_cost':cost,'page':moves,'balances':balances})

@login_required
@permission_required('core.operate_stock',raise_exception=True)
def product_edit(request,pk=None):
    obj=get_object_or_404(Product,pk=pk) if pk else None
    form=ProductForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        try:
            product=save_product(actor=request.user,pk=pk,data=form.cleaned_data)
            messages.success(request,'Produto salvo.');return redirect(return_url(request, url_reverse('product_detail', args=[product.pk])))
        except ValidationError as error:form.add_error(None,error)
        except IntegrityError:form.add_error(None,'SKU já utilizado. Atualize a página.')
    return render(request,'inventory/form.html',{'form':form,'title':'Editar produto' if pk else 'Novo produto'})

@login_required
@permission_required('core.operate_stock',raise_exception=True)
@require_POST
def product_remove(request,pk):
    messages.success(request,remove_product(actor=request.user,pk=pk));return redirect(return_url(request))

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
            set_components(actor=request.user,kit_id=pk,items=items);return redirect(return_url(request, url_reverse('product_detail', args=[pk])))
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
            messages.success(request,'Movimento confirmado.');return redirect(detail_url(request, 'operation_detail', op.pk))
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
                messages.success(request,'Estorno registrado.');return redirect(detail_url(request, 'operation_detail', new.pk))
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


@login_required
@permission_required('core.operate_stock', raise_exception=True)
@require_POST
def product_inactivate(request, pk):
    messages.success(request, inactivate_product(actor=request.user, pk=pk))
    return redirect(return_url(request))


@login_required
@permission_required('core.operate_stock', raise_exception=True)
def product_count(request, pk, location_id):
    from .forms import CountForm
    from .counting import count_snapshot, apply_count
    require(request.user, 'core.adjust_stock')
    product = get_object_or_404(Product, pk=pk, active=True, kind='SIMPLE')
    location = get_object_or_404(StockLocation, pk=location_id, active=True)
    token = count_snapshot(request.user, product, location)
    balance = StockBalance.objects.filter(product=product, location=location).first()
    form = CountForm(request.POST or None, initial={'snapshot': token})
    if request.method == 'POST' and form.is_valid():
        try:
            result = apply_count(actor=request.user, product_id=pk, location_id=location_id, **form.cleaned_data)
            messages.success(request, 'Contagem registrada. ' + ('Ajuste aplicado ao depósito.' if result['operation'] else 'Saldo conferido, sem diferença.'))
            return redirect(return_url(request))
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
    return render(request, 'inventory/count.html', {'form': form, 'product': product, 'location': location, 'balance': balance})


@login_required
def pricing(request, pk=None):
    from django import forms
    from apps.accounts.access import master
    from apps.products.pricing import configure_pricing
    master(request.user)
    product = get_object_or_404(Product, pk=pk) if pk else None
    class PricingForm(forms.Form):
        markup = forms.DecimalField(label='Markup individual (%)' if product else 'Markup geral (%)', required=not bool(product), min_value=0, max_digits=8, decimal_places=2,
            help_text='Vazio usa o markup geral. Zero é um percentual válido.' if product else 'Aplicado aos produtos sem percentual individual. Preço = custo médio da loja Mercadovet × (1 + markup/100).')
    initial = product.markup if product else Company.objects.get(pk=1).default_markup
    form = PricingForm(request.POST or None, initial={'markup':initial})
    if request.method == 'POST' and form.is_valid():
        configure_pricing(actor=request.user, markup=form.cleaned_data['markup'], product_id=pk)
        messages.success(request, 'Markup atualizado. Os preços da loja acompanham o custo médio da Mercadovet; vendas anteriores permanecem iguais.')
        return redirect(return_url(request, url_reverse('products')))
    return render(request, 'inventory/form.html', {'form':form, 'title':f'Preço de venda · {product}' if product else 'Preços de venda · markup geral'})


@login_required
def reconcile_inventory(request):
    from django import forms
    from django.utils.crypto import constant_time_compare
    from uuid import uuid4
    from apps.accounts.access import master
    from .reconciliation import reconcile
    master(request.user)
    from .forms import InventoryUploadForm as UploadForm
    from .spreadsheet import snapshot_from_xlsx
    form = UploadForm(request.POST or None, request.FILES or None)
    report = None
    token = None
    try:
        if request.method == 'POST' and request.POST.get('action') == 'apply':
            preview = request.session.get('inventory_reconciliation_preview', {})
            if not preview or not constant_time_compare(request.POST.get('token',''), preview['token']):
                raise ValidationError('Prévia expirada. Envie o arquivo novamente.')
            report = reconcile(actor=request.user, raw=preview['raw'], commit=True, expected_revision=preview['revision'])
            del request.session['inventory_reconciliation_preview']
            form = UploadForm()
            messages.success(request, 'Posição de estoque atualizada. Histórico e custos das vendas anteriores foram preservados.')
        elif request.method == 'POST' and form.is_valid():
            uploaded = form.cleaned_data['file']
            request.session.pop('inventory_reconciliation_preview', None)
            if uploaded.size > 5_000_000:
                raise ValidationError('Arquivo excede 5 MB.')
            content = uploaded.read()
            if uploaded.name.lower().endswith('.xlsx'):
                raw = snapshot_from_xlsx(content, **{k:form.cleaned_data[k] for k in ('location','mode','base_date','complete')})
            elif uploaded.name.lower().endswith('.json'):
                raw = content.decode('utf-8-sig')
            else:
                raise ValidationError('Envie Excel (.xlsx) ou o arquivo JSON legado.')
            report = reconcile(actor=request.user, raw=raw)
            token = str(uuid4())
            request.session['inventory_reconciliation_preview'] = dict(raw=raw,revision=report['revision'],token=token)
    except (ValidationError, UnicodeDecodeError) as exc:
        form.add_error(None, '; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Arquivo deve usar UTF-8.')
    return render(request, 'inventory/reconcile.html', {'form':form,'report':report,'token':token})


@login_required
def inventory_template(request):
    from apps.accounts.access import master
    from .spreadsheet import template_xlsx
    from django.http import HttpResponse
    master(request.user)
    response = HttpResponse(template_xlsx(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="modelo_estoque_mvet.xlsx"'
    return response
