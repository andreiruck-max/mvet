from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, F, Count
from datetime import timedelta
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET
from apps.inventory.services import domain_lock
from apps.products.models import Product
from apps.finance.selectors import cash_summary
from apps.finance.models import FinancialTitle
from apps.purchases.models import Purchase
from . import forms, selectors
from .datasets import metrics_for, sales_dataset

def bind(request,cls):
    form=cls(request.GET or {'period':'month'})
    valid=form.is_valid()
    if valid:
        data = form.data.copy()
        for field in ('start', 'end'):
            if form.cleaned_data.get(field): data[field] = form.cleaned_data[field].isoformat()
        form.data = data
    return form,form.cleaned_data if valid else None

def links(d):
    if not d:return ''
    return urlencode({'start':d['start'].isoformat(),'end':d['end'].isoformat()})

@login_required
@permission_required('core.view_dashboard',raise_exception=True)
@require_GET
@transaction.atomic
def dashboard(request):
    domain_lock();form,d=bind(request,forms.PeriodForm);ctx={'form':form}
    if d:
        ctx.update(totals=metrics_for(request.user,selectors.sales_summary(selectors.sale_rows(d))),channels=[metrics_for(request.user,r) for r in selectors.channel_summary(d)],dates=links(d),channel=d.get('channel'),range=d)
        if request.user.has_perm('core.view_dre'):ctx['dre']=selectors.dre({**d, 'channel': None})
        if request.user.has_perm('core.view_purchase_reports'):
            ctx['purchases'] = Purchase.objects.filter(date__range=(d['start'],d['end']),status__in=['ORDERED','RECEIVED']).aggregate(amount=Sum('total'),count=Count('pk'))
        if request.user.has_perm('core.view_costs'):ctx['stock']=Product.objects.aggregate(value=Sum('value'))['value'] or 0
        if request.user.has_perm('core.view_finance'):
            today=timezone.localdate();horizon=today+timedelta(days=30)
            ctx['forecast_dates']=links({'start':today,'end':horizon})
            ctx['cash_today']=cash_summary(today,today)['actual']
            projection=cash_summary(today,horizon)
            ctx['cash_projected']=projection['projected']
            ctx['unallocated']=projection['unallocated']
            ctx['overdue']=FinancialTitle.objects.filter(direction='PAY',status='OPEN',due_date__lt=today).aggregate(value=Sum(F('amount')-F('settled')))['value'] or selectors.ZERO
            ctx['payables']=selectors.payable_totals(selectors.payables({**d,'status':'pending'}))
    template='reporting/dashboard.html'
    return render(request,template,ctx,status=200 if d else 400)

@login_required
@permission_required('core.view_sales_report',raise_exception=True)
@require_GET
@transaction.atomic
def sales_sheet(request):
    domain_lock();form,d=bind(request,forms.SalesForm);ctx={'form':form}
    if d:
        # Company cards describe the period, independently of the selected channel/NF.
        company_data = {**d, 'channel': None, 'q': '', 'status': 'CONFIRMED'}
        ctx['company_totals'] = metrics_for(request.user, selectors.sales_summary(selectors.sale_rows(company_data)))
        from apps.sales.models import SalesChannel
        channel_values = {row['id']:row for row in selectors.channel_summary(company_data)}
        ctx['channels'] = [metrics_for(request.user, channel_values.get(channel.pk, dict(id=channel.pk,name=channel.name,**selectors.metrics({})))) for channel in SalesChannel.objects.filter(active=True)]
        ctx['channels'].sort(key=lambda row: (-row['revenue'], row['name'].casefold()))
        rows = selectors.sale_rows(d).order_by(
            'channel__name', 'channel_id', d.get('sort') or 'date',
            'invoice_length', 'invoice_number', 'invoice_series', 'pk').prefetch_related('items__product')
        page = Paginator(rows, 50).get_page(request.GET.get('page'))
        groups = []
        for sale in page:
            if not groups or groups[-1]['id'] != sale.channel_id:
                channel_rows = rows.filter(channel_id=sale.channel_id)
                groups.append({'id': sale.channel_id, 'name': str(sale.channel or 'Sem canal'), 'rows': [],
                               'totals': metrics_for(request.user, selectors.sales_summary(channel_rows))})
            groups[-1]['rows'].append(sale)
        from .sales_sheet import columns, decorate
        cols=columns(request.user,rows);decorate(groups,cols,rows)
        ctx.update(page=page, groups=groups, columns=cols, totals=metrics_for(request.user, selectors.sales_summary(rows)))
    return render(request,'reporting/sales.html',ctx,status=200 if d else 400)

@login_required
@permission_required('core.view_dre',raise_exception=True)
@require_GET
@transaction.atomic
def dre(request):
    domain_lock();form,d=bind(request,forms.PeriodForm)
    from .drilldown import lines
    report=selectors.dre(d) if d else None
    return render(request,'reporting/dre.html',{'form':form,'report':report,'range':d,'lines':lines(report,d,request.user.is_superuser) if d else []},status=200 if d else 400)

@login_required
@require_GET
@transaction.atomic
def dre_sources(request):
    from apps.accounts.access import master
    from .drilldown import sources
    master(request.user);domain_lock()
    form,d=bind(request,forms.PeriodForm)
    ctx={'form':form}
    if d:
        spec,rows,total=sources(request.GET.get('source',''),d)
        back_params={'start':d['start'].isoformat(),'end':d['end'].isoformat()}
        if d.get('channel'):back_params['channel']=d['channel'].pk
        path=(spec.get('snapshot') or {}).get('path',[])
        new_expense=reverse('expense_new')+('?' + urlencode({'category':path[-1]['id']}) if path else '')
        ctx.update(label=spec['label'],page=Paginator(rows,50).get_page(request.GET.get('page')),total=total,range=d,back=reverse('dre')+'?'+urlencode(back_params),new_expense=new_expense)
    return render(request,'reporting/dre_sources.html',ctx,status=200 if d else 400)

@login_required
@permission_required('core.view_finance',raise_exception=True)
@require_GET
@transaction.atomic
def purchase_payables(request):
    domain_lock();form=forms.PayablesForm(request.GET or {'period':'future','status':'pending'});d=form.cleaned_data if form.is_valid() else None;ctx={'form':form}
    if d:
        rows=selectors.payables(d)
        months,suppliers=selectors.payable_groups(rows)
        rows=rows.prefetch_related('purchase_installment__purchase__items','purchase_installment__purchase__installments')
        ctx.update(page=Paginator(rows,50).get_page(request.GET.get('page')),totals=selectors.payable_totals(rows),months=months,suppliers=suppliers)
    return render(request,'reporting/payables.html',ctx,status=200 if d else 400)

@login_required
@permission_required('core.view_dashboard',raise_exception=True)
@require_GET
@transaction.atomic
def dashboard_api(request):
    domain_lock();form,d=bind(request,forms.PeriodForm)
    if not d:return JsonResponse({'errors':form.errors.get_json_data()},status=400)
    return JsonResponse({'start':d['start'],'end':d['end'],'sales':metrics_for(request.user,selectors.sales_summary(selectors.sale_rows(d))),'channels':[metrics_for(request.user,r) for r in selectors.channel_summary(d)]})

@login_required
@permission_required('core.view_dre',raise_exception=True)
@require_GET
@transaction.atomic
def dre_api(request):
    domain_lock();form,d=bind(request,forms.PeriodForm)
    if not d:return JsonResponse({'errors':form.errors.get_json_data()},status=400)
    return JsonResponse(selectors.dre(d))
