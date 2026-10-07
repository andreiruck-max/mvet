from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from apps.core.services import require
from . import bulk


@login_required
@require_POST
def review(request,kind):
    if kind not in ('SALE','PURCHASE'):return HttpResponseBadRequest('Tipo inválido.')
    require(request.user,'core.review_bling' if kind=='SALE' else 'core.operate_purchases')
    if kind=='SALE':require(request.user,'core.approve_bling')
    back='bling_queue' if kind=='SALE' else 'bling_purchase_queue'
    try:
        selection=request.POST.get('selection','')
        if not selection:
            if request.POST.get('scope')=='all':selection=request.POST.get('all_selection','')
            else:
                pairs=[]
                for value in request.POST.getlist('selected'):pairs+=bulk.decode(request.user,kind,value)
                selection=bulk.token(request.user,kind,pairs)
        pairs=bulk.decode(request.user,kind,selection)
    except ValidationError as exc:
        messages.error(request,'; '.join(exc.messages));return redirect(back)
    form=bulk.BulkForm(request.POST if request.POST.get('preview') or request.POST.get('apply') else None,kind=kind)
    preview=False
    if form.is_bound and form.is_valid():
        if request.POST.get('apply'):
            try:
                count=bulk.apply(actor=request.user,kind=kind,selection=selection,action=form.cleaned_data['action'],reason=form.cleaned_data['reason'],changes=form.changes())
                messages.success(request,f'{count} notas atualizadas. Estoque e financeiro não foram movimentados.');return redirect(back)
            except ValidationError as exc:form.add_error(None,exc)
        else:preview=True
    # Names are read for display; signed revisions are checked again on application.
    model=bulk.InvoiceImport if kind=='SALE' else bulk.PurchaseInvoiceImport
    rows=model.objects.filter(pk__in=[p[0] for p in pairs])
    changes=[(form.fields[k].label,str(form.cleaned_data[k])) for k in form.changes()] if preview else []
    return render(request,'integrations/bulk.html',dict(form=form,kind=kind,selection=selection,count=len(pairs),rows=rows[:100],preview=preview,changes=changes,back=back))
