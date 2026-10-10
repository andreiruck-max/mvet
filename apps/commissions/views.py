from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from apps.sales.models import Sale
from . import forms,services as s,selectors as q
from .models import CommissionPlan,CommissionSettings,Payee,Entry,Payment,Installment

def error(form,exc):form.add_error(None,exc if isinstance(exc,ValidationError) else 'Registro duplicado ou alterado. Reabra a página.')

@login_required
@require_http_methods(['GET'])
def index(request,review=False):
    form=forms.FilterForm(request.GET,actor=request.user)
    s.access(request.user)
    rows=q.filtered(request.user,form.cleaned_data) if form.is_valid() else []
    people=q.payees(request.user);month=timezone.localdate().replace(day=1)
    events=Entry.objects.filter(installment__plan__payee__in=people)
    paid=Payment.objects.filter(payee__in=people)
    cards={'released':s.total(events.filter(date__gte=month),'released'),'paid':s.total(paid.filter(date__gte=month),'amount'),
        'pending':s.total(events,'released')-s.total(paid,'amount'),'received':events.filter(date__gte=month,received__gt=0).values('installment').distinct().count(),
        'people':sum(s.balance(p)>0 for p in people)}
    return render(request,'commissions/index.html',{'form':form,'page':Paginator(rows,50).get_page(request.GET.get('page')),'cards':cards,'review':review},status=200 if form.is_valid() else 400)

@login_required
@require_http_methods(['GET'])
def detail(request,pk):
    plan=q.decorate(get_object_or_404(q.plans(request.user),pk=pk))
    events=Entry.objects.filter(installment__plan=plan).select_related('installment','command__actor','reversal').order_by('-date','-pk')
    from apps.core.models import AuditLog
    history=AuditLog.objects.filter(entity='commissions.CommissionPlan',entity_id=str(plan.pk)).select_related('actor')
    return render(request,'commissions/detail.html',{'plan':plan,'events':events,'history':history})

@login_required
@require_http_methods(['GET','POST'])
def create(request,sale_id=None):
    s.manage(request.user)
    if sale_id:
        previous=CommissionPlan.objects.filter(sale_id=sale_id).first()
        if previous:return redirect('commission_detail',pk=previous.pk)
    initial={'sale':sale_id,'reason':'Comissão definida para a venda.'}
    if sale_id:
        sale=get_object_or_404(Sale,pk=sale_id)
        imported=getattr(sale,'bling_import',None)
        if imported:initial['customer']=getattr(imported,'customer_name','')
    form=forms.PlanForm(request.POST if request.method=='POST' else None,initial=initial)
    if request.method=='POST' and form.is_valid():
        d=form.cleaned_data
        try:plan=s.create_plan(actor=request.user,sale_id=d['sale'].pk,payee_id=d['payee'].pk,customer=d['customer'],rate=d['rate'],installments=d['installments'],key=d['key'],reason=d['reason'])
        except (ValidationError,IntegrityError) as exc:error(form,exc)
        else:messages.success(request,'Comissão prevista criada; o custo da venda foi atualizado.');return redirect('commission_detail',pk=plan.pk)
    defaults=CommissionSettings.objects.filter(pk=1).first()
    return render(request,'commissions/form.html',{'form':form,'title':'Definir comissão da venda','help':'Frete fica fora da base. O total substitui a comissão da venda na DRE. As parcelas controlam apenas a liberação, sem gerar contas a receber ou movimento bancário.','defaults':defaults,'payees':Payee.objects.filter(active=True)})

@login_required
@require_http_methods(['GET','POST'])
def action(request,pk,kind):
    s.manage(request.user);plan=None
    if kind=='receive':
        item=get_object_or_404(Installment.objects.select_related('plan'),pk=pk);plan=item.plan
        form=forms.ReceiptForm(request.POST if request.method=='POST' else None,initial={'amount':item.amount-s.total(item.entries,'received')})
        title=f'Registrar recebimento · parcela {item.number}';help='Registro para liberar comissão. Não gera entrada bancária nem conta a receber.'
    elif kind=='adjust':
        plan=get_object_or_404(CommissionPlan,pk=pk)
        form=forms.AdjustForm(request.POST if request.method=='POST' else None,initial={'revision':plan.revision,'rate':plan.rate,'override_total':plan.override_total})
        title='Ajustar comissão';help='Ajusta o custo da venda e registra a diferença liberada hoje. Pagamentos anteriores permanecem preservados.'
    elif kind=='reverse_receipt':
        event=get_object_or_404(Entry.objects.select_related('installment__plan'),pk=pk);plan=event.installment.plan
        form=forms.ReverseForm(request.POST if request.method=='POST' else None);title='Estornar recebimento';help='Comissão já paga pode gerar saldo negativo a compensar.'
    elif kind=='reverse_payment':
        get_object_or_404(Payment,pk=pk)
        form=forms.ReverseForm(request.POST if request.method=='POST' else None);title='Estornar pagamento de comissão';help='Registra a devolução / correção efetiva e reabre o saldo, preservando o pagamento original.'
    else:
        from django.http import Http404
        raise Http404
    if request.method=='POST' and form.is_valid():
        try:
            kwargs={'actor':request.user,**form.cleaned_data}
            if kind=='receive':s.receive(installment_id=pk,**kwargs)
            elif kind=='adjust':s.adjust(plan_id=pk,**kwargs)
            elif kind=='reverse_receipt':s.reverse_receipt(entry_id=pk,**kwargs)
            else:s.reverse_payment(payment_id=pk,**kwargs)
        except (ValidationError,IntegrityError) as exc:error(form,exc)
        else:
            messages.success(request,'Operação registrada com histórico.')
            return redirect('commission_detail',pk=plan.pk) if plan else redirect('commission_payments')
    return render(request,'commissions/form.html',{'form':form,'title':title,'help':help,'plan':plan})

@login_required
@require_http_methods(['GET','POST'])
def payment(request):
    s.manage(request.user);form=forms.PaymentForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        d=dict(form.cleaned_data);payee=d.pop('payee')
        try:s.pay(actor=request.user,payee_id=payee.pk,**d)
        except (ValidationError,IntegrityError) as exc:error(form,exc)
        else:messages.success(request,'Pagamento registrado e alocado às liberações mais antigas do período.');return redirect('commission_payments')
    return render(request,'commissions/form.html',{'form':form,'title':'Registrar pagamento de comissão','help':'Registre somente pagamento efetivamente realizado. A alocação é automática, das liberações mais antigas até o mês escolhido, descontando compensações. Não gera outro débito bancário ou despesa na DRE.'})

@login_required
@require_http_methods(['GET'])
def payments(request):
    rows=Payment.objects.filter(payee__in=q.payees(request.user)).select_related('payee','command__actor','reversal').prefetch_related('allocations__entry__installment__plan__sale')
    return render(request,'commissions/payments.html',{'page':Paginator(rows,50).get_page(request.GET.get('page'))})

@login_required
@require_http_methods(['GET'])
def monthly(request):
    s.access(request.user)
    form=forms.MonthForm(request.GET if request.GET else {'month':timezone.localdate().strftime('%Y-%m')},actor=request.user)
    rows=[];events=[];start=end=None
    if form.is_valid():rows,events,start,end=q.monthly(request.user,form.cleaned_data['month'],form.cleaned_data.get('payee'))
    return render(request,'commissions/monthly.html',{'form':form,'rows':rows,'events':events,'start':start,'end':end},status=200 if form.is_valid() else 400)

@login_required
@require_http_methods(['GET','POST'])
def settings(request,pk=None):
    s.manage(request.user);obj=get_object_or_404(Payee,pk=pk) if pk else None
    form=forms.PayeeForm(request.POST if request.method=='POST' and request.POST.get('action')=='payee' else None,instance=obj)
    config=CommissionSettings.objects.filter(pk=1).first()
    default=forms.DefaultForm(request.POST if request.method=='POST' and request.POST.get('action')=='default' else None,initial={'rate':config.default_rate if config else 0})
    if request.method=='POST':
        current=default if request.POST.get('action')=='default' else form
        if current.is_valid():
            try:
                if current is default:s.configure_default(actor=request.user,**default.cleaned_data)
                else:s.configure(actor=request.user,data=form.cleaned_data,pk=pk)
            except (ValidationError,IntegrityError) as exc:error(current,exc)
            else:messages.success(request,'Configuração salva. Percentuais de vendas anteriores foram preservados.');return redirect('commission_settings')
    return render(request,'commissions/settings.html',{'form':form,'default_form':default,'payees':Payee.objects.select_related('user'),'editing':obj})
