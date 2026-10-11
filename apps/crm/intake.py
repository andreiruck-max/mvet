"""Bounded, random, persistent first-contact releases. Follow-ups are independent."""
import random
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.accounts.access import master
from apps.core.services import audit
from apps.inventory.services import domain_lock
from .models import Contact, Interaction, IntakeSettings, FirstContactRelease
from .services import access, owners, event, state_snapshot


def settings():
    return IntakeSettings.objects.get_or_create(pk=1, defaults={'starts_on':timezone.localdate()})[0]


@transaction.atomic
def configure(*, actor, daily_limit, paused, starts_on, revision):
    master(actor);domain_lock()
    obj=settings()
    obj=IntakeSettings.objects.select_for_update().get(pk=obj.pk)
    if obj.revision != revision:
        raise ValidationError('A configuração mudou. Reabra a tela antes de salvar.')
    fields=('daily_limit','paused','starts_on')
    before={k:str(getattr(obj,k)) for k in fields}
    obj.daily_limit=daily_limit;obj.paused=paused;obj.starts_on=starts_on;obj.revision+=1
    obj.full_clean();obj.save()
    audit(actor,obj,'crm_intake_settings',before,{k:str(getattr(obj,k)) for k in fields})
    return obj


@transaction.atomic
def release_today(*, actor):
    access(actor);domain_lock()
    config=settings();today=timezone.localdate()
    if config.paused or config.starts_on>today or not config.daily_limit:
        return 0
    available=max(0,config.daily_limit-FirstContactRelease.objects.filter(day=today).count())
    if not available:
        return 0
    candidates=Contact.objects.filter(awaiting_first_release=True,last_at__isnull=True,
        state__in=['ACTIVE','PAUSED'],next_date__lte=today,owner__in=owners(),first_release__isnull=True).annotate(
        has_history=Exists(Interaction.objects.filter(contact_id=OuterRef('pk')))).filter(has_history=False)
    ids=list(candidates.order_by('pk').values_list('pk',flat=True))
    selected=random.SystemRandom().sample(ids,min(available,len(ids)))
    for obj in Contact.objects.select_for_update().filter(pk__in=selected).order_by('pk'):
        before=state_snapshot(obj)
        FirstContactRelease.objects.create(contact=obj,owner=obj.owner,triggered_by=actor,day=today)
        obj.awaiting_first_release=False;obj.state='ACTIVE';obj.next_date=today
        obj.next_reason='Primeiro contato · distribuição diária'
        event(actor,obj,'primeiro_contato_liberado',before,'Liberação automática conforme limite definido pelo Master; seleção aleatória.')
    return len(selected)
