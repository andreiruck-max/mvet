from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, F
from datetime import timedelta
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET
from apps.inventory.services import domain_lock
from apps.products.models import Product
from apps.finance.selectors import daily_cash
from apps.finance.models import FinancialTitle
from . import forms, selectors
from .datasets import metrics_for, sales_dataset

def bind(request,cls):
    form=cls(request.GET or {'period':'month'})
    valid=form.is_valid()
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
        if request.user.has_perm('core.view_dre'):ctx['dre']=selectors.dre(d)
        if request.user.has_perm('core.view_costs'):ctx['stock']=Product.objects.aggregate(value=Sum('value'))['value'] or 0
        if request.user.has_perm('core.view_finance'):
            today=timezone.localdate();horizon=today+timedelta(days=30);rows,unallocated=daily_cash(today,horizon)
            ctx['cash_today']=sum((r['final'] for r in rows if r['date']==today),selectors.ZERO)
            ctx['cash_projected']=sum((r['projected'] for r in rows if r['date']==horizon),selectors.ZERO)
            ctx['unallocated']=unallocated
            ctx['overdue']=FinancialTitle.objects.filter(direction='PAY',status='OPEN',due_date__lt=today).aggregate(value=Sum(F('amount')-F('settled')))['value'] or selectors.ZERO
            ctx['payables']=selectors.payable_totals(selectors.payables({**d,'status':'pending'}))
    template='reporting/dashboard.html' if request.user.has_perm('core.view_margins') and request.user.has_perm('core.view_costs') else 'reporting/revenue.html'
    return render(request,template,ctx,status=200 if d else 400)

@login_required
@permission_required('core.view_sales_report',raise_exception=True)
@require_GET
@transaction.atomic
def sales_sheet(request):
    domain_lock();form,d=bind(request,forms.SalesForm);ctx={'form':form}
    if d:
        rows=selectors.sale_rows(d)
        ctx.update(page=Paginator(rows,30).get_page(request.GET.get('page')),totals=selectors.sales_summary(rows))
    if d and not (request.user.has_perm('core.view_margins') and request.user.has_perm('core.view_costs')):
        from django.core.exceptions import ValidationError
        try:dataset=sales_dataset(request.user,d,page_rows=ctx['page'].object_list)
        except ValidationError as error:
            form.add_error(None,error);return render(request,'reporting/restricted_sales.html',{'form':form},status=400)
        ctx['page'].object_list=dataset.rows
        ctx.update(dataset=dataset,totals=dataset.totals)
        return render(request,'reporting/restricted_sales.html',ctx)
    return render(request,'reporting/sales.html',ctx,status=200 if d else 400)

@login_required
@permission_required('core.view_dre',raise_exception=True)
@require_GET
@transaction.atomic
def dre(request):
    domain_lock();form,d=bind(request,forms.PeriodForm)
    return render(request,'reporting/dre.html',{'form':form,'report':selectors.dre(d) if d else None,'range':d},status=200 if d else 400)

@login_required
@permission_required('core.view_finance',raise_exception=True)
@require_GET
@transaction.atomic
def purchase_payables(request):
    domain_lock();form,d=bind(request,forms.PayablesForm);ctx={'form':form}
    if d:
        rows=selectors.payables(d);ctx.update(page=Paginator(rows,30).get_page(request.GET.get('page')),totals=selectors.payable_totals(rows))
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
