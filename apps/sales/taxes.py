"""Dated tax revisions. Historic recalculation is explicit, atomic and audited."""
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone
from apps.core.services import require, audit
from apps.inventory.services import domain_lock, number
from .models import TaxRule, TaxRateChange, Sale, SaleTaxRevision

CENT=Decimal('0.01')

def effective_terms(rule,date):
    change=rule.changes.filter(effective_from__lte=date).first()
    return (change.rate,change.base,change.pk) if change else (rule.rate,rule.base,None)

def calculate_tax(sale):
    rule=TaxRule.objects.get(pk=sale.tax_rule_id) if sale.tax_rule_id else None
    rate,base_type,version=effective_terms(rule,sale.date) if rule else (None,None,None)
    base=sale.revenue if base_type=='REVENUE' else sale.products_amount-sale.discount
    snapshot={'rule_id':rule.pk if rule else None,'name':rule.name if rule else 'Manual','rate':str(rate) if rule else None,'base_type':base_type,'base_amount':str(base),'version_id':version,'override':sale.tax_override is not None,'reason':sale.tax_reason}
    amount=sale.tax_override if sale.tax_override is not None else (base*rate/100).quantize(CENT,rounding=ROUND_HALF_UP)
    return amount,snapshot

def affected_sales(rule,effective_from):
    if effective_from>=timezone.localdate():return Sale.objects.none()
    following=rule.changes.filter(effective_from__gt=effective_from).order_by('effective_from').first()
    rows=Sale.objects.filter(tax_rule=rule,status='CONFIRMED',tax_override__isnull=True,date__gte=effective_from)
    if following:rows=rows.filter(date__lt=following.effective_from)
    return rows

@transaction.atomic
def change_rate(*,actor,rule_id,rate,effective_from,base,reason,revision):
    require(actor,'core.manage_configuration');domain_lock()
    rule=TaxRule.objects.select_for_update().get(pk=rule_id)
    latest=rule.changes.order_by('-pk').first()
    if revision!=(latest.pk if latest else 0):raise ValidationError('A regra mudou em outra sessão. Reabra a edição.')
    number(rate,Decimal('0.0001'),zero=True)
    if rate>100:raise ValidationError('Alíquota deve estar entre 0 e 100%.')
    if effective_from<rule.starts_on or (rule.ends_on and effective_from>rule.ends_on):raise ValidationError('A data deve estar dentro da vigência da regra.')
    if not reason.strip():raise ValidationError('Informe o motivo da alteração.')
    change=TaxRateChange(rule=rule,rate=rate,effective_from=effective_from,base=base,reason=reason,actor=actor)
    change.full_clean();change.save()
    count=0
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.tax_revision', %s, true)",[str(change.pk)])
    try:
        for sale in affected_sales(rule,effective_from).select_for_update().order_by('pk').iterator():
            amount,new_snapshot=calculate_tax(sale)
            revision_row=SaleTaxRevision.objects.create(sale=sale,change=change,before_amount=sale.tax_amount,after_amount=amount,before_snapshot=sale.tax_snapshot,after_snapshot=new_snapshot)
            before={'tax_amount':str(sale.tax_amount),'tax_snapshot':sale.tax_snapshot}
            sale.tax_amount=amount;sale.tax_snapshot=new_snapshot;sale.save(update_fields=['tax_amount','tax_snapshot'])
            audit(actor,sale,'recalculate_sale_tax',before,{'tax_amount':str(amount),'tax_snapshot':new_snapshot,'revision_id':revision_row.pk,'reason':reason})
            count+=1
    finally:
        if connection.vendor=='postgresql':
            with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.tax_revision', '', true)")
    audit(actor,change,'change_tax_rate',{}, {'rule_id':rule.pk,'rate':str(rate),'effective_from':str(effective_from),'base':base,'reason':reason,'recalculated':count})
    return change,count
