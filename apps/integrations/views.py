import secrets
import time
from urllib.parse import urlencode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_POST
from apps.accounts.access import master
from apps.core.services import require
from apps.sales.forms import ExtraCosts, MasterExtraCosts
from apps.sales.services import EDIT_FIELDS
from . import bling, services
from .forms import QueryForm, ReviewForm, AliasForm, DecisionForm
from .models import BlingConnection, InvoiceImport, ImportRun


@login_required
@permission_required('core.review_bling', raise_exception=True)
def queue(request):
    rows = InvoiceImport.objects.select_related('sale')
    state = request.GET.get('status', 'PENDING')
    if state in dict(InvoiceImport._meta.get_field('status').choices): rows = rows.filter(status=state)
    if request.GET.get('q'): rows = rows.filter(number__icontains=request.GET['q'][:30])
    if request.GET.get('divergence') == '1': rows = rows.filter(discrepancy=True)
    return render(request, 'integrations/queue.html', {
        'page': Paginator(rows, 30).get_page(request.GET.get('page')), 'state': state,
        'states': InvoiceImport._meta.get_field('status').choices, 'query_form': QueryForm(),
        'runs': ImportRun.objects.all()[:10], 'connection': BlingConnection.objects.filter(pk=1).first(),
    })


@login_required
@permission_required('core.review_bling', raise_exception=True)
def detail(request, pk):
    invoice = get_object_or_404(InvoiceImport.objects.select_related('sale', 'connection'), pk=pk)
    form = ReviewForm(request.POST if request.method == 'POST' else None, invoice=invoice, actor=request.user)
    extra_class = MasterExtraCosts if request.user.is_superuser else ExtraCosts
    extras = extra_class(request.POST if request.method == 'POST' else None, prefix='extras')
    if request.method == 'POST':
        require(request.user, 'core.approve_bling')
        require(request.user, 'core.operate_sales'); require(request.user, 'core.confirm_sales')
        valid = form.is_valid(); extras_valid = extras.is_valid()
        if valid and extras_valid:
            try:
                costs = [(f.cleaned_data['name'], f.cleaned_data['amount']) for f in extras if f.cleaned_data and f.cleaned_data.get('name') and not f.cleaned_data.get('DELETE')]
                services.approve(actor=request.user, invoice_id=pk, revision=form.cleaned_data['revision'],
                    data={k: form.cleaned_data[k] for k in EDIT_FIELDS}, extra_costs=costs, reviewed=form.cleaned_data['reviewed'],
                    purpose_reviewed=form.cleaned_data['purpose_reviewed'])
                messages.success(request, 'Venda confirmada no MVet. Nenhuma alteração foi enviada ao Bling.')
                return redirect('bling_detail', pk=pk)
            except ValidationError as exc: form.add_error(None, exc)
            except IntegrityError: form.add_error(None, 'NF/série ou chave já cadastrada. Confira a venda existente; não crie outra.')
    rows = [{'source': r, 'product': services.resolve(invoice.connection, r)} for r in invoice.source.get('items', [])]
    return render(request, 'integrations/detail.html', {'invoice': invoice, 'rows': rows, 'form': form,
        'extra_formset': extras, 'alias_form': AliasForm(initial={'revision': invoice.revision}, prefix='alias'),
        'decision_form': DecisionForm(initial={'revision': invoice.revision}, prefix='decision')})


@login_required
@require_POST
def query(request):
    require(request.user, 'core.review_bling'); require(request.user, 'core.fetch_bling')
    wants_json = request.headers.get('Accept') == 'application/json'
    form = QueryForm(request.POST)
    if form.is_valid():
        try:
            run = bling.sync_page(actor=request.user, **form.cleaned_data)
            if wants_json:
                # Invalid documents remain visible; transport/partial failures stop on this page.
                blocked = bool(run.message) or (run.has_more and run.page >= 10000)
                return JsonResponse({'page': run.page, 'processed': run.processed, 'errors': run.errors,
                    'has_more': run.has_more, 'blocked': blocked,
                    'next_page': run.page if blocked else (run.page + 1 if run.has_more else None),
                    'message': run.message or ('Limite de páginas atingido. Reduza o período.' if blocked else '')})
            messages.info(request, f'Página {run.page}: {run.processed} notas consultadas; {run.errors} erros. ' + (run.message or ('Consulte a próxima página.' if run.has_more else 'Fim desta consulta.')))
        except ValidationError as exc:
            if wants_json: return JsonResponse({'message': '; '.join(exc.messages)}, status=400)
            messages.error(request, '; '.join(exc.messages))
    else:
        if wants_json: return JsonResponse({'message': 'Informe um período e situação válidos.', 'errors': form.errors.get_json_data()}, status=400)
        messages.error(request, 'Informe período e página válidos.')
    return redirect('bling_queue')


@login_required
@require_POST
def alias(request, pk):
    require(request.user, 'core.review_bling'); require(request.user, 'core.map_bling_products')
    get_object_or_404(InvoiceImport, pk=pk)
    form = AliasForm(request.POST, prefix='alias')
    if form.is_valid():
        try:
            services.map_product(actor=request.user, invoice_id=pk, **form.cleaned_data)
            messages.success(request, 'Código vinculado. Confira os produtos antes de confirmar a venda.')
        except ValidationError as exc: messages.error(request, '; '.join(exc.messages))
    else: messages.error(request, 'Informe código, unidade e produto válidos.')
    return redirect('bling_detail', pk=pk)


@login_required
@require_POST
def decision(request, pk, action):
    require(request.user, 'core.review_bling'); get_object_or_404(InvoiceImport, pk=pk)
    try:
        if action == 'refresh': bling.refresh_invoice(actor=request.user, invoice_id=pk)
        elif action in ('ignore', 'reopen'):
            form = DecisionForm(request.POST, prefix='decision')
            if not form.is_valid(): raise ValidationError('Informe motivo e revisão válidos.')
            services.set_ignored(actor=request.user, invoice_id=pk, ignored=action == 'ignore', **form.cleaned_data)
        else: raise ValidationError('Ação inválida.')
    except ValidationError as exc: messages.error(request, '; '.join(exc.messages))
    return redirect('bling_detail', pk=pk)


@login_required
@never_cache
def connection(request):
    master(request.user)
    problem = ''
    try: bling.configured()
    except ValidationError as exc: problem = '; '.join(exc.messages)
    return render(request, 'integrations/connection.html', {'connection': BlingConnection.objects.filter(pk=1).first(), 'problem': problem})


@login_required
@require_POST
@never_cache
def connect(request):
    master(request.user)
    try: bling.configured()
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages)); return redirect('bling_connection')
    state = secrets.token_urlsafe(32)
    request.session['bling_oauth'] = {'state': state, 'created': time.time()}
    return HttpResponseRedirect(bling.AUTHORIZE + '?' + urlencode({'response_type': 'code', 'client_id': settings.BLING_CLIENT_ID, 'state': state}))


@login_required
@never_cache
@sensitive_variables('code')
def callback(request):
    master(request.user)
    pending = request.session.pop('bling_oauth', None)
    state = request.GET.get('state', '')
    if not pending or time.time() - pending['created'] > 600 or not secrets.compare_digest(pending['state'], state):
        messages.error(request, 'Autorização expirada ou inválida. Inicie novamente no MVet.')
    elif request.build_absolute_uri(request.path) != settings.BLING_REDIRECT_URI:
        messages.error(request, 'O endereço de retorno difere da configuração do servidor. Inicie a conexão no endereço configurado.')
    elif request.GET.get('error') or not request.GET.get('code'):
        messages.error(request, 'Autorização não concedida.')
    else:
        try: bling.authorize(actor=request.user, code=request.GET['code'])
        except ValidationError as exc: messages.error(request, '; '.join(exc.messages))
        else: messages.success(request, 'Conexão autorizada. Consulte notas para conferir o emitente e os dados.')
    response = redirect('bling_connection'); response['Referrer-Policy'] = 'no-referrer'
    return response


@login_required
@require_POST
def disconnect(request):
    bling.disconnect(actor=request.user)
    messages.success(request, 'Conexão local removida. Notas e vendas preservadas. Para revogar o aplicativo, use o Bling.')
    return redirect('bling_connection')
