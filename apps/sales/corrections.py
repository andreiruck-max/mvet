"""Audited corrections, including explicit relocation of historical stock exits."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone
from apps.inventory.models import StockOperation, StockLocation
from apps.products.models import Product
from apps.accounts.access import master
from apps.core.services import audit
from apps.inventory.services import domain_lock, number, _apply, _date, _fingerprint
from apps.finance.models import FinancialTitle
from .models import Sale, SaleCorrection, SalesChannel

FIELDS=('products_amount','discount','shipping_received','shipping_paid','fees','difal','commission','other_costs')
SNAPSHOT_FIELDS=(*FIELDS,'tax_amount','tax_snapshot')

def snapshot(sale):
    values = {name:getattr(sale,name) if name=='tax_snapshot' else str(getattr(sale,name)) for name in SNAPSHOT_FIELDS}
    values.update(channel_id=sale.channel_id, location_id=sale.location_id, stock_operation_id=sale.stock_operation_id,
                  channel_name=str(sale.channel), location_name=str(sale.location))
    return values


def relocate(sale, location, actor, key, reason):
    original = sale.stock_operation
    if not original or original.kind != 'SALE_OUT' or StockOperation.objects.filter(reversal_of=original).exists():
        raise ValidationError('Saída de estoque ausente ou já estornada. Confira o histórico da venda.')
    moves = list(original.movements.select_related('location').order_by('pk'))
    if not moves or any(m.location_id != sale.location_id or m.quantity >= 0 for m in moves):
        raise ValidationError('Saída de estoque incompatível com o depósito da venda.')
    if -sum((m.value + m.cost_variance for m in moves), Decimal(0)) != sale.cmv:
        raise ValidationError('Saída de estoque não corresponde ao CMV histórico.')
    products = {p.pk:p for p in Product.objects.select_for_update().filter(pk__in=[m.product_id for m in moves]).order_by('pk')}
    if any(not p.active for p in products.values()):
        raise ValidationError('Há produto inativo. Revise o cadastro antes de trocar o depósito.')
    today = timezone.localdate()
    _date(today, products.values())
    returned = StockOperation.objects.create(kind='SALE_RETURN', date=today, actor=actor, reason=reason,
        reversal_of=original, fingerprint=_fingerprint(['correct_sale_return', sale.pk, str(key)]))
    for m in moves:
        _apply(returned, products[m.product_id], m.location, -m.quantity, -(m.value+m.cost_variance), unit_cost=m.unit_cost)
    outgoing = StockOperation.objects.create(kind='SALE_OUT', date=today, actor=actor, reason=reason,
        reversal_of=returned, fingerprint=_fingerprint(['correct_sale_location', sale.pk, str(key)]))
    for m in moves:
        _apply(outgoing, products[m.product_id], location, m.quantity, m.value+m.cost_variance, unit_cost=m.unit_cost)
    return outgoing


@transaction.atomic
def correct_sale(*,actor,sale_id,revision,key,reason,values,channel_id=None,location_id=None):
    master(actor);domain_lock();key=UUID(str(key));reason=reason.strip()
    if not reason or len(reason)>500:raise ValidationError('Informe o motivo da correção (até 500 caracteres).')
    if set(values)!=set(FIELDS):raise ValidationError('Campos de correção inválidos.')
    values={name:number(value,Decimal('.01'),zero=True) for name,value in values.items()}
    sale=Sale.objects.select_for_update().get(pk=sale_id)
    channel_id = sale.channel_id if channel_id is None else int(channel_id)
    location_id = sale.location_id if location_id is None else int(location_id)
    prior=SaleCorrection.objects.filter(key=key).first()
    if prior:
        if prior.sale_id!=sale.pk or prior.actor_id!=actor.pk or prior.before_revision!=revision or prior.reason!=reason or any(Decimal(prior.after[name])!=value for name,value in values.items()):
            raise ValidationError('Envio já utilizado com outros dados.')
        if prior.after.get('channel_id', sale.channel_id) != channel_id or prior.after.get('location_id', sale.location_id) != location_id:
            raise ValidationError('Envio já utilizado com outro canal ou depósito.')
        if sale.revision!=revision+1 or sale.status!='CONFIRMED':raise ValidationError('Esta correção já foi executada; reabra a venda.')
        return sale
    if sale.status!='CONFIRMED' or sale.revision!=revision:raise ValidationError('A venda mudou ou não está confirmada. Reabra a página.')
    channel = SalesChannel.objects.filter(pk=channel_id).first()
    location = StockLocation.objects.filter(pk=location_id).first()
    if not channel or (channel_id != sale.channel_id and not channel.active):
        raise ValidationError('Selecione um canal ativo.')
    if not location or (location_id != sale.location_id and not location.active):
        raise ValidationError('Selecione um depósito ativo.')
    managed_plan = getattr(sale, 'commission_plan', None)
    if managed_plan and values['commission'] != sale.commission:
        raise ValidationError('Comissão controlada por parcelas: use Comissões → Ajustar comissão.')
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
    if location_id != sale.location_id:
        sale.stock_operation = relocate(sale, location, actor, key, reason)
    sale.channel = channel
    sale.location = location
    if managed_plan:
        from apps.commissions.services import sync_sale_values
        sync_sale_values(sale,actor,reason)
    after=snapshot(sale)
    if before==after:raise ValidationError('Nenhum valor, canal ou depósito foi alterado.')
    entry=SaleCorrection.objects.create(key=key,sale=sale,actor=actor,reason=reason,before_revision=revision,before=before,after=after)
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.sale_correction', %s, true)",[str(key)])
    try:
        sale.revision+=1;sale.save(update_fields=[*SNAPSHOT_FIELDS,'channel','location','stock_operation','revision'])
    finally:
        if connection.vendor=='postgresql':
            with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.sale_correction', '', true)")
    audit(actor,sale,'correct_sale_values',before,dict(after,reason=reason,correction_id=entry.pk))
    return sale
