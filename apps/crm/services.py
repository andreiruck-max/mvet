import re
from datetime import timedelta
from uuid import UUID
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.accounts.access import master
from apps.core.services import require, audit
from apps.inventory.services import domain_lock
from .models import Contact, ContactEvent, Interaction, InactivationRequest, RecurrenceRule
from . import choices as c


def phone_number(value):
    raw=str(value or '').strip()
    if not raw:return ''
    if re.search(r'[^\d\s()+.\-]',raw):raise ValidationError('Telefone inválido. Informe DDD e número; para exterior use + e código do país.')
    digits=re.sub(r'\D','',raw)
    if raw.startswith('+'):
        if not 8<=len(digits)<=15:raise ValidationError('Telefone internacional inválido.')
    elif len(digits) in (10,11):digits='55'+digits
    elif len(digits) not in (12,13) or not digits.startswith('55'):
        raise ValidationError('Informe telefone com DDD (10 ou 11 dígitos).')
    return digits


def access(actor,contact=None):
    require(actor,'core.operate_crm')
    if contact and not actor.is_superuser and contact.owner_id!=actor.pk:raise PermissionDenied


def owners():
    return get_user_model().objects.filter(pk__in=[u.pk for u in get_user_model().objects.filter(is_active=True) if u.has_perm('core.operate_crm')])


def validate_owner(owner):
    if not owner or not owner.is_active or not owner.has_perm('core.operate_crm'):
        raise ValidationError('Responsável deve ser um usuário ativo com acesso ao CRM.')


def state_snapshot(contact):
    return {'state':contact.state,'next_date':str(contact.next_date or ''),'next_reason':contact.next_reason,'owner':contact.owner_id,'revision':contact.revision}


def event(actor,contact,action,before,note=''):
    contact.revision+=1;contact.full_clean();contact.save()
    after=state_snapshot(contact)
    ContactEvent.objects.create(contact=contact,actor=actor,action=action,note=note,before=before,after=after)
    audit(actor,contact,'crm_'+action,before,after)


def locked(actor,pk,revision):
    access(actor);domain_lock()
    contact=Contact.objects.select_for_update().get(pk=pk);access(actor,contact)
    if contact.revision!=revision:raise ValidationError('Este contato mudou em outra sessão. Reabra a ficha antes de continuar.')
    return contact


def future_date(value):
    if not value or value<timezone.localdate():raise ValidationError('Escolha uma data de hoje em diante.')
    return value


def duplicates(phone,email,pk=None):
    query=Q(pk__in=[])
    if phone:query|=Q(phone=phone)
    if email:query|=Q(email__iexact=email)
    return Contact.objects.exclude(pk=pk).filter(query).exists()


@transaction.atomic
def save_contact(*,actor,data,pk=None,revision=0):
    access(actor);domain_lock()
    obj=locked(actor,pk,revision) if pk else Contact(owner=actor,next_date=timezone.localdate())
    before=state_snapshot(obj) if pk else {}
    fields=('name','phone','email','city','uf','company','segment','origin','kind','notes','commercial_info')
    old={k:getattr(obj,k) for k in fields}
    for key in fields:
        if key in data:setattr(obj,key,str(data[key] or '').strip())
    obj.phone=phone_number(obj.phone);obj.email=obj.email.casefold();obj.uf=obj.uf.upper()
    if duplicates(obj.phone,obj.email,pk):raise ValidationError('Possível duplicidade: telefone ou e-mail já cadastrado. Peça ao Master para conferir a carteira; nenhum novo contato foi criado.')
    if actor.is_superuser and data.get('owner'):obj.owner=data['owner']
    elif data.get('owner') and data['owner'].pk!=actor.pk:raise PermissionDenied
    if not pk or (actor.is_superuser and data.get('owner')):validate_owner(obj.owner)
    if not pk:obj.next_date=future_date(data.get('first_date') or timezone.localdate())
    obj.full_clean();obj.save()
    event(actor,obj,'cadastro' if not pk else 'edicao',before)
    audit(actor,obj,'crm_profile',old,{k:getattr(obj,k) for k in fields})
    return obj


@transaction.atomic
def record(*,actor,pk,revision,key,data):
    access(actor);domain_lock()
    try:key=UUID(str(key))
    except (ValueError,TypeError):raise ValidationError('Identificador de envio inválido.')
    prior=Interaction.objects.filter(key=key).first()
    if prior:
        access(actor,prior.contact)
        if prior.actor_id!=actor.pk or prior.contact_id!=pk:raise PermissionDenied
        if any(getattr(prior,k)!=data.get(k,'') for k in ('occurred_at','channel','kind','sent','received','read_state','result','internal_note')):
            raise ValidationError('Envio já utilizado com outro conteúdo. Reabra o formulário.')
        if prior.manual_date!=bool(data.get('next_date')) or (prior.manual_date and prior.next_date!=data['next_date']) or (data.get('next_reason') and prior.next_reason!=data['next_reason']):
            raise ValidationError('Envio já utilizado com outra próxima ação. Reabra o formulário.')
        return prior
    obj=locked(actor,pk,revision)
    if obj.state in ('DNC','INACTIVE','APPROVAL'):raise ValidationError('Contato fora da rotina. Resolva a aprovação ou reativação antes de registrar uma abordagem.')
    occurred=data['occurred_at']
    if occurred>timezone.now():raise ValidationError('Data do contato não pode estar no futuro.')
    if obj.last_at and occurred<obj.last_at:raise ValidationError('Não registre um contato anterior ao último histórico. Use observação interna para contexto antigo.')
    result=data['result'];rule=RecurrenceRule.objects.get(result=result)
    manual=data.get('next_date')
    if manual and not rule.allow_manual and not actor.is_superuser:raise ValidationError('O Master não permite alterar a data para esse resultado.')
    if manual:future_date(manual)
    next_date=manual or (timezone.localdate(occurred)+timedelta(days=rule.days))
    reason=data.get('next_reason') or dict(c.RESULTS)[result]
    before=state_snapshot(obj)
    obj.state='WAITING' if result=='WAITING' else 'ACTIVE'
    if result=='OPT_OUT':obj.state='DNC';next_date=None;reason='Pedido explícito para não contatar'
    item=Interaction(contact=obj,actor=actor,key=key,next_date=next_date,next_reason=reason,rule_days=rule.days,manual_date=bool(manual),**{k:data.get(k,'') for k in ('occurred_at','channel','kind','sent','received','read_state','result','internal_note')})
    item.full_clean();item.save()
    obj.last_at=occurred;obj.last_result=result;obj.next_date=next_date;obj.next_reason=reason
    event(actor,obj,'contato_registrado',before)
    return item


@transaction.atomic
def change_state(*,actor,pk,revision,action,date=None,reason='',justification='',owner=None):
    obj=locked(actor,pk,revision);before=state_snapshot(obj)
    if action=='reactivate':
        master(actor);validate_owner(owner);future_date(date)
        if obj.state not in ('DNC','INACTIVE'):raise ValidationError('Somente contatos inativos ou não contatar podem ser reativados.')
        if not justification.strip():raise ValidationError('Justifique a reativação; para Não contatar, documente a nova autorização do contato.')
        obj.owner=owner;obj.state='ACTIVE';obj.next_date=date;obj.next_reason='Reativação: '+justification[:250]
    elif action=='dnc':
        if not justification.strip():raise ValidationError('Registre o pedido explícito para não contatar.')
        obj.state='DNC';obj.next_date=None;obj.next_reason='Não contatar'
        # DNC is immediate and supersedes an outstanding request, without deleting it.
        for req in obj.requests.filter(decision='PENDING'):
            req.decision='APPROVED';req.decided_by=actor;req.decided_at=timezone.now();req.decision_note='Bloqueio imediato: '+justification;req.save()
    else:
        if obj.state in ('DNC','INACTIVE','APPROVAL'):raise ValidationError('Contato fora da rotina. Reativação ou decisão do Master necessária.')
        if action in ('pause','reschedule'):
            if obj.last_result and not actor.is_superuser and not RecurrenceRule.objects.get(result=obj.last_result).allow_manual:
                raise ValidationError('A regra desse resultado reserva alterações de data ao Master.')
            future_date(date)
            if not justification.strip():raise ValidationError('Informe o motivo da próxima ação.')
            obj.state='PAUSED' if action=='pause' else 'ACTIVE';obj.next_date=date;obj.next_reason=justification[:300]
        elif action=='request':
            if reason=='OPT_OUT':raise ValidationError('Para pedido de não receber contato, use Não contatar: o bloqueio é imediato.')
            if not justification.strip():raise ValidationError('Justifique a solicitação.')
            req=InactivationRequest(contact=obj,actor=actor,reason=reason,justification=justification);req.full_clean(exclude=['decided_by','decided_at']);req.save()
            obj.state='APPROVAL';obj.next_date=None;obj.next_reason='Aguardando decisão do Master'
        else:raise ValidationError('Ação inválida.')
    event(actor,obj,action,before,justification)
    return obj


@transaction.atomic
def decide(*,actor,request_id,approve,date=None,note=''):
    master(actor);domain_lock()
    req=InactivationRequest.objects.select_for_update().select_related('contact').get(pk=request_id)
    if req.decision!='PENDING':raise ValidationError('Solicitação já decidida. Atualize a página.')
    obj=Contact.objects.select_for_update().get(pk=req.contact_id)
    if obj.state!='APPROVAL':raise ValidationError('O estado do contato mudou. Atualize a página.')
    before=state_snapshot(obj)
    obj.state='INACTIVE' if approve else 'ACTIVE';obj.next_date=None if approve else future_date(date)
    obj.next_reason='Inativação aprovada' if approve else 'Retorno definido pelo Master'
    req.decision='APPROVED' if approve else 'REJECTED';req.decided_by=actor;req.decided_at=timezone.now();req.decision_note=note;req.save()
    event(actor,obj,'inativacao_aprovada' if approve else 'inativacao_recusada',before,note)
    return obj


@transaction.atomic
def save_rules(*,actor,rows):
    master(actor);domain_lock()
    expected=set(RecurrenceRule.objects.exclude(result='OPT_OUT').values_list('pk',flat=True))
    if len(rows)!=len(expected) or {row['id'] for row in rows}!=expected:raise ValidationError('Conjunto de regras inválido. Reabra a página.')
    for row in rows:
        rule=RecurrenceRule.objects.select_for_update().get(pk=row['id'])
        before={'days':rule.days,'allow_manual':rule.allow_manual}
        rule.days=row['days'];rule.allow_manual=row['allow_manual'];rule.full_clean();rule.save()
        audit(actor,rule,'crm_rule',before,{'days':rule.days,'allow_manual':rule.allow_manual})
