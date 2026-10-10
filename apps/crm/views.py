import csv
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from apps.accounts.access import master
from . import forms, services, selectors, importing
from .models import Contact, Interaction, RecurrenceRule, InactivationRequest, ImportBatch

def detail_object(request,pk):return get_object_or_404(selectors.contacts(request.user),pk=pk)
def error(form,exc):form.add_error(None,'; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Cadastro duplicado. Confira telefone/e-mail.')

@login_required
@require_http_methods(['GET'])
def queue(request,all_contacts=False):
    form=forms.FilterForm(request.GET,actor=request.user);rows=selectors.filtered(request.user,form.cleaned_data) if form.is_valid() else selectors.contacts(request.user).none()
    today=timezone.localdate()
    if not all_contacts:
        rows=rows.filter(state__in=['ACTIVE','WAITING','PAUSED']).exclude(state='PAUSED',next_date__gt=today).order_by('next_date','name','pk')
    page=Paginator(rows,50).get_page(request.GET.get('page'));selectors.decorate(page.object_list)
    return render(request,'crm/queue.html',{'form':form,'page':page,'all_contacts':all_contacts,'today':today},status=200 if form.is_valid() else 400)

@login_required
@require_http_methods(['GET'])
def detail(request,pk):
    obj=detail_object(request,pk);selectors.decorate([obj])
    return render(request,'crm/detail.html',{'contact':obj,'page':Paginator(obj.interactions.select_related('actor'),30).get_page(request.GET.get('page')),'events':Paginator(obj.events.select_related('actor'),30).get_page(request.GET.get('events_page')),'latest':obj.interactions.first()})

@login_required
@require_http_methods(['GET','POST'])
def edit(request,pk=None):
    services.access(request.user);obj=detail_object(request,pk) if pk else None
    form=forms.ContactForm(request.POST if request.method=='POST' else None,actor=request.user,instance=obj,initial={'revision':obj.revision if obj else 0,'owner':request.user.pk})
    if request.method=='POST' and form.is_valid():
        try:obj=services.save_contact(actor=request.user,pk=pk,revision=form.cleaned_data['revision'],data=form.cleaned_data)
        except (ValidationError,IntegrityError) as exc:error(form,exc)
        else:messages.success(request,'Contato salvo e próxima ação preservada.');return redirect('crm_detail',pk=obj.pk)
    return render(request,'crm/form.html',{'form':form,'title':'Editar contato' if pk else 'Novo contato','contact':obj})

@login_required
@require_http_methods(['GET','POST'])
def interaction(request,pk):
    obj=detail_object(request,pk)
    form=forms.InteractionForm(request.POST if request.method=='POST' else None,initial={'revision':obj.revision,'occurred_at':timezone.localtime().replace(second=0,microsecond=0),'channel':'WHATSAPP','kind':'CONVERSATION','read_state':'UNKNOWN'})
    if request.method=='POST' and form.is_valid():
        try:services.record(actor=request.user,pk=pk,revision=form.cleaned_data['revision'],key=form.cleaned_data['key'],data=form.cleaned_data)
        except (ValidationError,IntegrityError) as exc:error(form,exc)
        else:messages.success(request,'Contato registrado. A próxima ação foi atualizada.');return redirect('crm_detail',pk=pk)
    return render(request,'crm/interaction.html',{'form':form,'contact':obj,'latest':obj.interactions.first(),'rules':{r.result:{'days':r.days,'manual':r.allow_manual or request.user.is_superuser} for r in RecurrenceRule.objects.all()},'today':str(timezone.localdate())})

@login_required
@require_http_methods(['GET','POST'])
def state(request,pk,action):
    obj=detail_object(request,pk)
    titles={'pause':'Pausar até uma data','reschedule':'Reagendar contato','request':'Solicitar inativação','dnc':'Não contatar','reactivate':'Reativar contato'}
    if action not in titles:
        from django.http import Http404
        raise Http404
    if action=='reactivate':master(request.user)
    form=forms.StateForm(request.POST if request.method=='POST' else None,action=action,initial={'revision':obj.revision,'owner':obj.owner_id})
    if request.method=='POST' and form.is_valid():
        try:services.change_state(actor=request.user,pk=pk,action=action,**form.cleaned_data)
        except ValidationError as exc:error(form,exc)
        else:messages.success(request,'Próxima ação / status atualizado.');return redirect('crm_detail',pk=pk)
    return render(request,'crm/form.html',{'form':form,'title':titles[action],'contact':obj,'help':'Não contatar bloqueia a rotina imediatamente. Reativar exige nova autorização documentada pelo Master.' if action in ('dnc','reactivate') else ''})

@login_required
@require_http_methods(['GET','POST'])
def rules(request):
    master(request.user);query=RecurrenceRule.objects.exclude(result='OPT_OUT').order_by('pk')
    formset=forms.Rules(request.POST if request.method=='POST' else None,queryset=query)
    if request.method=='POST' and formset.is_valid():
        try:services.save_rules(actor=request.user,rows=[{'id':f.instance.pk,'days':f.cleaned_data['days'],'allow_manual':f.cleaned_data['allow_manual']} for f in formset])
        except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
        else:messages.success(request,'Regras salvas. Valem para os próximos registros; datas existentes não foram alteradas.');return redirect('crm_rules')
    return render(request,'crm/rules.html',{'formset':formset})

@login_required
@require_http_methods(['GET','POST'])
def approvals(request,pk=None):
    master(request.user)
    req=get_object_or_404(InactivationRequest.objects.select_related('contact','actor'),pk=pk) if pk else None
    form=forms.DecisionForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and req and form.is_valid():
        try:services.decide(actor=request.user,request_id=pk,approve=form.cleaned_data['decision']=='approve',date=form.cleaned_data['date'],note=form.cleaned_data['note'])
        except ValidationError as exc:error(form,exc)
        else:messages.success(request,'Decisão registrada.');return redirect('crm_approvals')
    from django.db.models import Prefetch
    rows=InactivationRequest.objects.filter(decision='PENDING').select_related('contact__owner','actor').annotate(attempts=Count('contact__interactions',filter=Q(contact__interactions__kind='ATTEMPT'))).order_by('created_at','pk').prefetch_related(Prefetch('contact__interactions',queryset=Interaction.objects.order_by('-occurred_at','-pk')[:3]))
    return render(request,'crm/approvals.html',{'page':Paginator(rows,30).get_page(request.GET.get('page')),'approval':req,'form':form})

@login_required
@require_http_methods(['GET'])
def report(request):
    master(request.user);form=forms.FilterForm(request.GET,actor=request.user)
    form.fields['start'].label='Atividades de';form.fields['end'].label='Até'
    d=form.cleaned_data if form.is_valid() else {};rows=selectors.filtered(request.user,{k:v for k,v in d.items() if k not in ('start','end')}) if form.is_valid() else Contact.objects.none()
    today=timezone.localdate();start=d.get('start') or today.replace(day=1);end=d.get('end') or today
    activities=Interaction.objects.filter(contact__in=rows)
    metrics={'today':activities.filter(occurred_at__date=today).count(),'period':activities.filter(occurred_at__date__range=(start,end)).count(),'overdue':rows.filter(state__in=['ACTIVE','WAITING','PAUSED'],next_date__lt=today).count(),'due':rows.filter(state__in=['ACTIVE','WAITING','PAUSED'],next_date=today).count(),'waiting':rows.filter(state='WAITING').count(),'new':rows.filter(created_at__date__range=(start,end)).count(),'requests':rows.filter(state='APPROVAL').count()}
    missing=rows.filter(state__in=['ACTIVE','WAITING','PAUSED'],next_date__isnull=True)
    return render(request,'crm/report.html',{'form':form,'metrics':metrics,'start':start,'end':end,'owners':rows.values('owner__username').annotate(count=Count('pk')).order_by('-count'),'missing':missing,'inactive_owners':rows.filter(owner__is_active=False).exclude(state__in=['INACTIVE','DNC']),'activity_owners':activities.filter(occurred_at__date__range=(start,end)).values('actor__username').annotate(count=Count('pk')).order_by('-count')},status=200 if form.is_valid() else 400)

@login_required
@require_http_methods(['GET','POST'])
def import_contacts(request,batch_id=None):
    master(request.user);batch=get_object_or_404(ImportBatch,pk=batch_id) if batch_id else None
    form=forms.ImportForm(request.POST if request.method=='POST' else None,request.FILES or None)
    if request.method=='POST':
        try:
            if batch:
                if request.POST.get('confirm')!='yes':raise ValidationError('Confirme explicitamente a importação das linhas válidas.')
                batch=importing.commit(actor=request.user,batch_id=batch.pk)
                messages.success(request,'Importação concluída. Confira o resultado por linha.');return redirect('crm_import_preview',batch_id=batch.pk)
            elif form.is_valid():
                batch=importing.preview(actor=request.user,upload=form.cleaned_data['file'],owner=form.cleaned_data['owner'],first_date=form.cleaned_data['first_date'])
                return redirect('crm_import_preview',batch_id=batch.pk)
        except (ValidationError,IntegrityError,ValueError,csv.Error) as exc:
            messages.error(request,'; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Arquivo inválido. Confira o formato e os valores.')
    return render(request,'crm/import.html',{'form':form,'batch':batch,'valid_count':sum(not r['error'] for r in batch.rows) if batch else 0})
