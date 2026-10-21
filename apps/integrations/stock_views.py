from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from django.shortcuts import render, redirect
from django.urls import reverse
from urllib.parse import urlencode
from django.views.decorators.http import require_http_methods
from apps.accounts.access import master
from apps.products.models import Product
from apps.inventory.models import StockLocation
from . import stock_comparison as service
from .models import BlingStockCorrection, BlingComparisonCache


class CompareForm(forms.Form):
    location = forms.ModelChoiceField(label='Depósito MVet', queryset=StockLocation.objects.filter(active=True))
    deposit = forms.ChoiceField(label='Depósito Bling')
    q = forms.CharField(label='SKU exato', max_length=100, required=False)
    differences = forms.BooleanField(label='Somente diferenças nesta página', required=False)


class CorrectForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    field = forms.ChoiceField(label='O que corrigir', choices=[('price', 'Preço de venda'), ('quantity', 'Saldo físico')])
    direction = forms.ChoiceField(label='Sistema que será corrigido', choices=[('mvet', 'Corrigir MVet usando o Bling'), ('bling', 'Corrigir Bling usando o MVet')])
    reason = forms.CharField(label='Motivo', max_length=350)


@login_required
@require_http_methods(['GET', 'POST'])
def comparison(request):
    master(request.user)
    error = None
    rows = []
    page = None
    preview = None
    correct = CorrectForm(request.POST or None)
    cache, _ = BlingComparisonCache.objects.get_or_create(actor=request.user)
    saved = cache.payload
    params = dict(saved.get('params', {}))
    params.update(request.GET.dict())
    if request.GET.get('refresh') == '1':
        params = request.GET.dict()
        params.setdefault('page', '1')
    form = CompareForm(params or None)
    consulted_at = None
    try:
        if request.method == 'POST':
            if request.POST.get('action') == 'acknowledge':
                try: correction_id = int(request.POST.get('correction', ''))
                except ValueError: raise ValidationError('Tentativa inválida.')
                service.acknowledge(actor=request.user, correction_id=correction_id, reason=request.POST.get('reason', ''))
                messages.success(request, 'Conferência registrada. Consulte os valores novamente antes de qualquer nova correção.')
                return redirect('bling_stock_comparison')
            if request.POST.get('action') == 'confirm':
                try: approved = signing.loads(request.POST.get('approval', ''), salt='bling.correction.approval', max_age=600)
                except signing.BadSignature: raise ValidationError('Confirmação expirada. Prepare a correção novamente.') from None
                result = service.apply(actor=request.user, **approved)
                if result.status == 'DONE':
                    update_saved_correction(cache, result, request.user)
                    messages.success(request, 'Correção concluída. Última consulta preservada.')
                elif result.status in ('UNKNOWN', 'PENDING'): messages.warning(request, 'Resultado pendente de conferência no Bling. A mesma solicitação não será reenviada. ' + result.message)
                else: messages.error(request, 'Correção não aplicada. ' + result.message)
                return redirect('bling_stock_comparison')
            if correct.is_valid():
                data = correct.cleaned_data
                snapshot = service.decode(request.user, data['token'])
                source = 'remote' if data['direction'] == 'mvet' else 'local'
                destination = 'local' if source == 'remote' else 'remote'
                preview = {'product': Product.objects.get(pk=snapshot['product']), 'field': dict(correct.fields['field'].choices)[data['field']],
                           'destination': data['direction'].upper(), 'before': snapshot[destination][data['field']],
                           'after': snapshot[source][data['field']], 'reason': data['reason'],
                           'location': StockLocation.objects.get(pk=snapshot['location']), 'deposit': snapshot['deposit'],
                           'approval': signing.dumps(data, salt='bling.correction.approval')}
        else:
            refresh = request.GET.get('refresh') == '1'
            choices = service.deposits() if refresh or not saved.get('deposits') else saved['deposits']
            form.fields['deposit'].choices = choices
            if params and form.is_valid():
                query_params = {k: str(params.get(k, '')) for k in ('location', 'deposit', 'q', 'page')}
                old_params = {k: str(saved.get('params', {}).get(k, '')) for k in query_params}
                if saved.get('rows') is not None and query_params == old_params and not refresh:
                    rows = saved['rows']
                    page = Paginator(range(saved['count']), 10).get_page(saved['page'])
                else:
                    products = Product.objects.filter(active=True, kind='SIMPLE').order_by('sku', 'pk')
                    query = form.cleaned_data['q'].strip()
                    if query: products = products.filter(sku=query)
                    page = Paginator(products, 10).get_page(params.get('page'))
                    rows = service.comparison(actor=request.user, products=list(page), location=form.cleaned_data['location'], deposit=form.cleaned_data['deposit'])
                    rows = [dict(r, product={'pk': r['product'].pk, 'sku': r['product'].sku, 'name': r['product'].name, 'unit': r['product'].unit}) for r in rows]
                    saved = {'rows': rows, 'count': page.paginator.count, 'page': page.number, 'deposits': choices,
                             'consulted_at': timezone.now().isoformat()}
                saved['params'] = {k: v for k, v in params.items() if k != 'refresh'}
                cache.payload = saved
                cache.save(update_fields=['payload'])
                if refresh:
                    return redirect(reverse('bling_stock_comparison') + '?' + urlencode(saved['params']))
                consulted_at = datetime.fromisoformat(saved['consulted_at'])
                if form.cleaned_data['differences']:
                    rows = [r for r in rows if r.get('error') or r['price_diff'] or r['stock_diff']]
    except (Product.DoesNotExist, StockLocation.DoesNotExist, BlingStockCorrection.DoesNotExist):
        error = 'Produto, depósito ou tentativa indisponível. Consulte novamente.'
    except ValidationError as exc:
        error = '; '.join(exc.messages)
    response = render(request, 'inventory/bling_comparison.html', {'form': form, 'correct': correct, 'rows': rows,
        'consulted_at': consulted_at, 'page': page, 'preview': preview, 'error': error, 'history': BlingStockCorrection.objects.select_related('product', 'actor').order_by('-pk')[:30]})
    response['Cache-Control'] = 'private, no-store'
    return response


def update_saved_correction(cache, result, actor):
    """Update only the confirmed field, retaining the original consultation date."""
    saved = cache.payload
    snapshot = result.snapshot
    for row in saved.get('rows', []):
        if not row.get('token') or service.decode(actor, row['token']) != snapshot:
            continue
        current = service.local(Product.objects.get(pk=result.product_id), StockLocation.objects.get(pk=snapshot['location']))
        remote = dict(snapshot['remote'])
        if result.direction == 'bling': remote[result.field] = snapshot['local'][result.field]
        fresh = dict(snapshot, local=current, remote=remote, key=str(uuid4()))
        row.update(local=current, remote=remote, token=signing.dumps(fresh, salt=service.SALT),
                   price_diff=Decimal(current['price']) != Decimal(remote['price']),
                   stock_diff=Decimal(current['quantity']) != Decimal(remote['quantity']))
    cache.payload = saved
    cache.save(update_fields=['payload'])


class NewProductForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    name = forms.CharField(label='Descrição', max_length=240)
    price = forms.DecimalField(label='Preço de venda (R$)', min_value=0, max_digits=14, decimal_places=2)
    include_stock = forms.BooleanField(label='Importar também o saldo físico mostrado acima', required=False)
    cost = forms.DecimalField(label='Custo unitário conferido (R$)', required=False, min_value=0, max_digits=18, decimal_places=6,
                              help_text='Obrigatório e maior que zero ao importar saldo positivo. Não copiamos o custo médio do Bling.')
    reason = forms.CharField(label='Motivo', max_length=350)


@login_required
@require_http_methods(['GET', 'POST'])
def catalog(request):
    master(request.user)
    rows, has_more, preview, token = [], False, None, None
    error = None
    class SearchForm(forms.Form):
        q = forms.CharField(label='Buscar no Bling', required=False, max_length=100)
        search = forms.ChoiceField(label='Pesquisar por', choices=[('name', 'Descrição'), ('sku', 'SKU exato')])
        location = forms.ModelChoiceField(label='Depósito MVet', queryset=StockLocation.objects.filter(active=True))
        deposit = forms.ChoiceField(label='Depósito Bling')
        page = forms.IntegerField(required=False, min_value=1, max_value=10000, widget=forms.HiddenInput)
    search = SearchForm(request.GET or None)
    form = NewProductForm(request.POST or None)
    page_number = 1
    try:
        if request.method == 'POST':
            if form.is_valid():
                product = service.create_product(actor=request.user, **form.cleaned_data)
                messages.success(request, f'Produto {product.sku} cadastrado no MVet.')
                return redirect('product_detail', pk=product.pk)
            if request.POST.get('token'): preview = service.decode_new(request.user, request.POST['token'])
        else:
            search.fields['deposit'].choices = service.deposits()
            if request.GET and search.is_valid():
                values = search.cleaned_data
                page_number = values['page'] or 1
                if request.GET.get('product'):
                    token = service.new_product_preview(actor=request.user, remote_id=request.GET['product'], location=values['location'], deposit=values['deposit'])
                    preview = service.decode_new(request.user, token)
                    form = NewProductForm(initial={'token': token, 'name': preview['source']['name'], 'price': preview['source']['price']})
                else:
                    rows, has_more = service.catalog(actor=request.user, query=values['q'], search=values['search'], page=page_number)
    except (Product.DoesNotExist, StockLocation.DoesNotExist, BlingStockCorrection.DoesNotExist):
        error = 'Produto, depósito ou tentativa indisponível. Consulte novamente.'
    except ValidationError as exc:
        error = '; '.join(exc.messages)
        if request.method == 'POST':
            try: preview = service.decode_new(request.user, request.POST.get('token', ''))
            except ValidationError: preview = None
    response = render(request, 'inventory/bling_catalog.html', {'search': search, 'form': form, 'rows': rows,
        'has_more': has_more, 'previous': page_number-1, 'next': page_number+1, 'preview': preview, 'error': error})
    response['Cache-Control'] = 'private, no-store'
    return response
