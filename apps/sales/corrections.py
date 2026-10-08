"""Audited monetary corrections, without replaying stock or invoice imports."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from apps.accounts.access import master
from apps.core.services import audit
from apps.inventory.services import domain_lock, number
from apps.finance.models import FinancialTitle
from .models import Sale, SaleCorrection

FIELDS=('products_amount','discount','shipping_received','shipping_paid','fees','difal','commission','other_costs')
SNAPSHOT_FIELDS=(*FIELDS,'tax_amount','tax_snapshot')

def snapshot(sale):
    return {name:getattr(sale,name) if name=='tax_snapshot' else str(getattr(sale,name)) for name in SNAPSHOT_FIELDS}

@transaction.atomic
def correct_sale(*,actor,sale_id,revision,key,reason,values):
    master(actor);domain_lock();key=UUID(str(key));reason=reason.strip()
    if not reason or len(reason)>500:raise ValidationError('Informe o motivo da correção (até 500 caracteres).')
    if set(values)!=set(FIELDS):raise ValidationError('Campos de correção inválidos.')
    values={name:number(value,Decimal('.01'),zero=True) for name,value in values.items()}
    sale=Sale.objects.select_for_update().get(pk=sale_id)
    prior=SaleCorrection.objects.filter(key=key).first()
    if prior:
        if prior.sale_id!=sale.pk or prior.actor_id!=actor.pk or prior.before_revision!=revision or prior.reason!=reason or any(Decimal(prior.after[name])!=value for name,value in values.items()):
            raise ValidationError('Envio já utilizado com outros dados.')
        if sale.revision!=revision+1 or sale.status!='CONFIRMED':raise ValidationError('Esta correção já foi executada; reabra a venda.')
        return sale
    if sale.status!='CONFIRMED' or sale.revision!=revision:raise ValidationError('A venda mudou ou não está confirmada. Reabra a página.')
    before=snapshot(sale)
    for name,value in values.items():setattr(sale,name,value)
    if sale.discount>sale.products_amount or sale.revenue<0:raise ValidationError('Desconto ou receita inválidos.')
    revenue_changed=any(before[name]!=str(getattr(sale,name)) for name in ('products_amount','discount','shipping_received'))
    if revenue_changed and FinancialTitle.objects.filter(sale=sale).exists():
        raise ValidationError('Esta venda possui recebível histórico. A receita exige conciliação específica; taxas e frete pago podem ser corrigidos.')
    # Use the historic tax terms, never silently replace them with today's rate.
    if revenue_changed and not sale.tax_snapshot.get('override'):
        terms=dict(sale.tax_snapshot)
        if terms.get('rate') is None:raise ValidationError('Imposto histórico sem alíquota; revisão específica necessária.')
        base=sale.revenue if terms['base_type']=='REVENUE' else sale.products_amount-sale.discount
        terms['base_amount']=str(base);sale.tax_snapshot=terms
        sale.tax_amount=(base*Decimal(terms['rate'])/100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    after=snapshot(sale)
    if before==after:raise ValidationError('Nenhum valor foi alterado.')
    entry=SaleCorrection.objects.create(key=key,sale=sale,actor=actor,reason=reason,before_revision=revision,before=before,after=after)
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.sale_correction', %s, true)",[str(key)])
    try:
        sale.revision+=1;sale.save(update_fields=[*SNAPSHOT_FIELDS,'revision'])
    finally:
        if connection.vendor=='postgresql':
            with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.sale_correction', '', true)")
    audit(actor,sale,'correct_sale_values',before,dict(after,reason=reason,correction_id=entry.pk))
    return sale
