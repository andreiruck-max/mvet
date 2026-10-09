from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from apps.core.models import Company
from apps.purchases.models import Supplier
from apps.purchases.forms import Installments
from apps.products.models import Product
from .models import PurchaseInvoiceImport, BlingConnection, ImportRun
from .purchase_forms import PurchaseQueryForm, PurchaseReviewForm, PurchaseProducts, ImportSupplierForm
from . import bling, purchase_services as services


@login_required
@permission_required('core.operate_purchases', raise_exception=True)
def queue(request):
    from . import bulk
    rows=bulk.filtered_rows('PURCHASE',request.GET)
    state=request.GET.get('status','pending')
    page=Paginator(rows,50).get_page(request.GET.get('page'))
    bulk_context=bulk.context(request.user,'PURCHASE',rows,page)
    return render(request, 'integrations/purchase_queue.html', dict(page=page, **bulk_context,
        query_form=PurchaseQueryForm(), state=state, runs=ImportRun.objects.filter(kind='PURCHASE')[:10], connection=BlingConnection.objects.filter(pk=1).first()))


@login_required
@permission_required(['core.operate_purchases', 'core.fetch_bling'], raise_exception=True)
@require_POST
def query(request):
    form = PurchaseQueryForm(request.POST)
    if not form.is_valid(): return JsonResponse({'message': 'Informe período e situação válidos.'}, status=400)
    try: run = bling.sync_page(actor=request.user, kind='PURCHASE', **form.cleaned_data)
    except ValidationError as exc: return JsonResponse({'message': '; '.join(exc.messages)}, status=400)
    blocked = bool(run.message) or (run.has_more and run.page >= 10000)
    return JsonResponse(dict(page=run.page, processed=run.processed, errors=run.errors, has_more=run.has_more,
        blocked=blocked, next_page=run.page if blocked else (run.page+1 if run.has_more else None), message=run.message))


@login_required
@permission_required('core.operate_purchases', raise_exception=True)
def detail(request, pk):
    invoice = get_object_or_404(PurchaseInvoiceImport.objects.select_related('purchase'), pk=pk)
    if request.method=='POST' and invoice.purchase_id:
        return redirect('purchase_detail',pk=invoice.purchase_id)
    source = invoice.source
    supplier = Supplier.objects.filter(document=source.get('supplier_document'), active=True).first() if source.get('supplier_document') else None
    company = Company.objects.filter(pk=1).first()
    initial = dict(revision=invoice.revision, supplier=supplier, freight=Decimal(source.get('freight', '0')),
                   location=company.default_stock_location_id if company else None)
    initial.update({k:v for k,v in invoice.review_overrides.items() if k in ('location','discount','freight','other_costs','acquisition_kind')})
    post = request.POST if request.method == 'POST' else None
    form = PurchaseReviewForm(post, initial=initial)
    if not request.user.has_perm('core.manage_suppliers'):form.fields.pop('create_supplier')
    new_supplier=ImportSupplierForm(post if post is not None and post.get('create_supplier') else None,
        prefix='new_supplier',initial=dict(legal_name=source.get('supplier_name',''),document=source.get('supplier_document',''),
            phone=source.get('supplier_phone',''),email=source.get('supplier_email',''),trade_name=source.get('supplier_trade_name','')))
    item_initial = [{'product': Product.objects.filter(sku=row['code'], active=True, kind='SIMPLE').first(),
        'new_sku':row['code'] if len(row['code'])<=60 else '', 'new_name':row['name'],'new_unit':'UN',
        'mode':invoice.review_overrides.get('item_mode','STOCK'),'category':invoice.review_overrides.get('category')} for row in source.get('items', [])]
    items = PurchaseProducts(post, initial=item_initial, prefix='products')
    schedule = [{'due_date': date.fromisoformat(row['date']), 'amount': Decimal(row['amount']), 'notes': ''} for row in source.get('installments', [])]
    bonus=(post.get('acquisition_kind') if post is not None else initial.get('acquisition_kind'))=='BONUS'
    if bonus:schedule=[]
    # Source parcels on a bonus are informative only; no payable is created.
    installments = Installments(None if bonus else post, initial=schedule, prefix='installments')
    if request.method == 'POST':
        valid = form.is_valid(); valid_items = items.is_valid(); valid_dates = True if bonus else installments.is_valid()
        valid_supplier=new_supplier.is_valid() if form.cleaned_data.get('create_supplier') else True
        if valid and valid_items and valid_dates and valid_supplier:
            try:
                data = dict(form.cleaned_data)
                creating=data.pop('create_supplier',False)
                if creating:data['supplier_data']=new_supplier.cleaned_data
                purchase = services.create_draft(actor=request.user, invoice_id=pk, products=[f.cleaned_data.get('product') for f in items],treatments=[f.cleaned_data for f in items],
                    installments=[] if bonus else [(f.cleaned_data['due_date'], f.cleaned_data['amount'], f.cleaned_data['notes']) for f in installments if f.cleaned_data and not f.cleaned_data.get('DELETE')], **data)
                messages.success(request, 'Rascunho importado. Confira parcelas, confirme a compra e registre o recebimento físico separadamente.')
                return redirect('purchase_detail', pk=purchase.pk)
            except ValidationError as exc: form.add_error(None, '; '.join(exc.messages))
            except IntegrityError: form.add_error(None, 'Documento/série já existe para o fornecedor. Confira a compra existente.')
    return render(request, 'integrations/purchase_detail.html', dict(invoice=invoice, form=form, items=items,
        rows=list(zip(source.get('items', []), items)), installments=installments, new_supplier=new_supplier))


@login_required
@permission_required(['core.operate_purchases', 'core.fetch_bling'], raise_exception=True)
@require_POST
def refresh(request, pk):
    invoice = get_object_or_404(PurchaseInvoiceImport.objects.select_related('connection'), pk=pk)
    try:
        payload = bling.read('/nfe/' + invoice.external_id).get('data')
        if not isinstance(payload, dict) or str(payload.get('id')) != invoice.external_id: raise ValidationError('Detalhe não corresponde à nota.')
        services.stage(actor=request.user, connection=invoice.connection, payload=payload)
    except ValidationError as exc: messages.error(request, '; '.join(exc.messages))
    return redirect('bling_purchase_detail', pk=pk)


@login_required
@permission_required('core.operate_purchases', raise_exception=True)
@require_POST
def decision(request, pk, action):
    get_object_or_404(PurchaseInvoiceImport, pk=pk)
    if action not in ('reject', 'reopen'):
        return JsonResponse({'message': 'Ação inválida.'}, status=400)
    try:
        revision = int(request.POST.get('revision', ''))
    except (TypeError, ValueError):
        return JsonResponse({'message': 'Revisão inválida.'}, status=400)
    try:
        services.set_rejected(actor=request.user, invoice_id=pk, revision=revision, rejected=action == 'reject')
        messages.success(request, 'Nota rejeitada e retirada das pendências.' if action == 'reject' else 'Nota reaberta.')
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('bling_purchase_detail', pk=pk)
    return redirect('bling_purchase_queue' if action == 'reject' else 'bling_purchase_detail', **({} if action == 'reject' else {'pk': pk}))
