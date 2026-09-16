"""Atomic stock operations. All mutations share the same lock order."""
import hashlib
import json
import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone
from apps.core.models import Company
from apps.core.services import require, audit
from apps.products.models import Product
from .models import StockBalance, StockLocation, StockMovement, StockOperation

QTY = Decimal('0.0001')
MONEY = Decimal('0.000001')
ZERO = Decimal('0')
KINDS = {'OPENING','RECEIPT','ISSUE','ADJUST_IN','ADJUST_OUT','TRANSFER','SPLIT','KIT_ISSUE','REVALUE'}
COST_KINDS = {'OPENING','RECEIPT','ADJUST_IN','REVALUE'}

def domain_lock():
    # Also taken by catalog/composition changes and opening imports. Short critical
    # sections serialize stock writes, including idempotency checks and kit expansion.
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [763820102])

def number(value, quantum, *, zero=False):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValidationError('Informe um número decimal válido.')
    if value < 0 or (not zero and value == 0) or value != value.quantize(quantum):
        raise ValidationError('Valor inválido ou com casas decimais excedentes.')
    if value >= Decimal('1000000000000'):
        raise ValidationError('Valor acima do limite permitido.')
    return value

def quant(value): return value.quantize(MONEY, rounding=ROUND_HALF_UP)

def _fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

def _repeat(key, fingerprint):
    previous = StockOperation.objects.filter(key=key).first()
    if previous and previous.fingerprint != fingerprint:
        raise ValidationError('Este envio já foi utilizado com outros dados. Reabra o formulário.')
    return previous

def _date(date, products, *, opening=False):
    company = Company.objects.get(pk=1)
    if date < company.cutover_date or date > timezone.localdate():
        raise ValidationError('Data fora do período entre o corte e hoje.')
    if opening and date != company.cutover_date:
        raise ValidationError('A abertura deve usar a data de corte.')
    for p in products:
        last = p.movements.order_by('-operation__date', '-pk').first()
        if opening and last:
            raise ValidationError(f'{p.sku}: abertura já realizada ou produto já movimentado.')
        if last and date < last.operation.date:
            raise ValidationError(f'{p.sku}: há movimento posterior. Registre um ajuste na data atual para preservar o histórico.')

def _value_out(p, quantity):
    if quantity > p.quantity:
        raise ValidationError(f'{p.sku}: estoque global insuficiente.')
    return p.value if quantity == p.quantity else min(p.value, quant(quantity*p.average_cost))

def _apply(operation, product, location, quantity, value, *, average_override=None, unit_cost=None):
    balance, _ = StockBalance.objects.get_or_create(product=product, location=location)
    balance = StockBalance.objects.select_for_update().get(pk=balance.pk)
    before_q, before_v, before_avg = product.quantity, product.value, product.average_cost
    next_q, next_v = before_q + quantity, before_v + value
    if balance.quantity + quantity < 0 or next_q < 0 or next_v < 0:
        raise ValidationError(f'{product.sku}: saldo insuficiente no local ou valor inconsistente.')
    if next_q == 0 and next_v != 0:
        raise ValidationError('Estoque zerado não pode conservar valor residual.')
    product.quantity, product.value = next_q, next_v
    product.average_cost = average_override if average_override is not None else (quant(next_v/next_q) if next_q else before_avg)
    product.full_clean()
    product.save(update_fields=['quantity','value','average_cost'])
    before_local = balance.quantity
    balance.quantity += quantity
    balance.save(update_fields=['quantity'])
    movement = StockMovement.objects.create(operation=operation, product=product, location=location,
        quantity=quantity, value=value, unit_cost=unit_cost if unit_cost is not None else (quant(abs(value/quantity)) if quantity else product.average_cost),
        before_quantity=before_q, after_quantity=next_q, before_value=before_v, after_value=next_v,
        before_average=before_avg, after_average=product.average_cost)
    audit(operation.actor, movement, operation.kind,
          {'quantity':str(before_q),'value':str(before_v),'local_quantity':str(before_local)},
          {'quantity':str(next_q),'value':str(next_v),'local_quantity':str(balance.quantity),'reason':operation.reason})
    return movement

@transaction.atomic
def execute(*, actor, key, kind, date, reason, product_id, location_id, quantity=ZERO,
            cost=None, target_location_id=None, target_product_id=None, target_quantity=None):
    require(actor,'core.operate_stock')
    if kind not in KINDS: raise ValidationError('Operação inválida.')
    if kind in COST_KINDS: require(actor,'core.view_costs')
    if not reason or not reason.strip() or len(reason)>500: raise ValidationError('Informe o motivo (até 500 caracteres).')
    try: key = uuid.UUID(str(key))
    except (ValueError, TypeError): raise ValidationError('Identificador de envio inválido.')
    number(quantity, QTY, zero=kind in {'OPENING','REVALUE'})
    if kind in COST_KINDS:
        number(cost, MONEY, zero=True)
    if kind == 'REVALUE' and quantity != 0: raise ValidationError('Correção de custo não altera quantidade.')
    if kind == 'SPLIT': number(target_quantity,QTY)
    fingerprint = _fingerprint([actor.pk,kind,date,reason,product_id,location_id,quantity,cost,target_location_id,target_product_id,target_quantity])
    domain_lock()
    previous = _repeat(key,fingerprint)
    if previous: return previous
    p = Product.objects.get(pk=product_id)
    components = list(p.components.select_related('component').order_by('component_id')) if kind=='KIT_ISSUE' else []
    ids = {p.pk}
    if target_product_id: ids.add(int(target_product_id))
    ids.update(c.component_id for c in components)
    products = {p.pk:p for p in Product.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
    p = products[p.pk]
    if len(products)!=len(ids) or any(not item.active for item in products.values()):
        raise ValidationError('Produto inexistente ou inativo.')
    location_ids = {int(location_id)}
    if target_location_id: location_ids.add(int(target_location_id))
    locations = {loc.pk:loc for loc in StockLocation.objects.select_for_update().filter(pk__in=location_ids).order_by('pk')}
    if len(locations)!=len(location_ids) or any(not loc.active for loc in locations.values()):
        raise ValidationError('Local inexistente ou inativo.')
    loc = locations[int(location_id)]
    if (kind=='KIT_ISSUE') != (p.kind=='KIT'):
        raise ValidationError('Use saída de kit para kits virtuais; demais operações exigem produto simples.')
    _date(date,products.values(),opening=kind=='OPENING')
    operation = StockOperation.objects.create(key=key,fingerprint=fingerprint,kind=kind,date=date,reason=reason.strip(),actor=actor)
    if kind in {'OPENING','RECEIPT','ADJUST_IN'}:
        _apply(operation,p,loc,quantity,quant(quantity*cost),average_override=cost if quantity==0 else None,unit_cost=cost)
    elif kind in {'ISSUE','ADJUST_OUT'}:
        _apply(operation,p,loc,-quantity,-_value_out(p,quantity))
    elif kind=='REVALUE':
        if p.quantity == 0:
            _apply(operation,p,loc,ZERO,ZERO,average_override=cost,unit_cost=cost)
        else:
            _apply(operation,p,loc,ZERO,quant(p.quantity*cost)-p.value,unit_cost=cost)
    elif kind=='TRANSFER':
        if not target_location_id or int(target_location_id)==loc.pk: raise ValidationError('Escolha outro local de destino.')
        value = _value_out(p,quantity)
        avg = p.average_cost
        _apply(operation,p,loc,-quantity,-value)
        _apply(operation,p,locations[int(target_location_id)],quantity,value,average_override=avg)
    elif kind=='SPLIT':
        if not target_product_id or int(target_product_id)==p.pk: raise ValidationError('Escolha outro produto de destino.')
        target = products[int(target_product_id)]
        if target.kind!='SIMPLE': raise ValidationError('O destino deve ser produto simples.')
        value = _value_out(p,quantity)
        _apply(operation,p,loc,-quantity,-value)
        _apply(operation,target,locations[int(target_location_id)] if target_location_id else loc,target_quantity,value)
    elif kind=='KIT_ISSUE':
        if not components: raise ValidationError('Cadastre os componentes do kit antes de movimentar.')
        for item in components:
            component = products[item.component_id]
            if component.kind!='SIMPLE': raise ValidationError('Kits aninhados não são permitidos.')
            consumed = number(item.quantity*quantity,QTY)
            _apply(operation,component,loc,-consumed,-_value_out(component,consumed))
    return operation

@transaction.atomic
def reverse(*,actor,operation_id,key,date,reason):
    require(actor,'core.operate_stock')
    require(actor,'core.view_costs')
    if not reason.strip() or len(reason)>500: raise ValidationError('Informe o motivo do estorno.')
    domain_lock()
    fingerprint=_fingerprint([actor.pk,'REVERSAL',operation_id,date,reason])
    previous=_repeat(key,fingerprint)
    if previous:return previous
    original=StockOperation.objects.get(pk=operation_id)
    if original.kind=='REVERSAL' or StockOperation.objects.filter(reversal_of=original).exists():
        raise ValidationError('Operação já estornada ou é um estorno.')
    moves=list(original.movements.order_by('-pk'))
    products={p.pk:p for p in Product.objects.select_for_update().filter(pk__in=[m.product_id for m in moves]).order_by('pk')}
    for p in products.values():
        if p.movements.order_by('-pk').first().operation_id!=original.pk:
            raise ValidationError('Há movimentos posteriores. Estorne-os primeiro ou registre um ajuste atual.')
    _date(date,products.values())
    operation=StockOperation.objects.create(key=key,fingerprint=fingerprint,kind='REVERSAL',date=date,reason=reason,actor=actor,reversal_of=original)
    for m in moves:
        _apply(operation,products[m.product_id],m.location,-m.quantity,-m.value,average_override=m.before_average,unit_cost=m.unit_cost)
    return operation
