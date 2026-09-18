from .models import SalesChannel
"""Sales authorization and atomic transitions; stock shares the inventory mutex."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.core.models import Company
from apps.core.services import require, audit
from apps.products.models import Product
from apps.inventory.models import StockLocation, StockOperation
from apps.inventory.services import domain_lock, number, QTY, _fingerprint, _apply, _value_out, quant, _date
from .models import Sale, SaleItem, SaleConsumption, SalesChannel, TaxRule, SaleExtraCost

FINANCIAL_FIELDS = ['products_amount','discount','shipping_received','shipping_paid','fees','difal','commission','other_costs']
EDIT_FIELDS = ['date','invoice_number','invoice_series','channel','location',*FINANCIAL_FIELDS,'tax_rule','tax_override','tax_reason','notes','revenue_adjustment','revenue_adjustment_reason']
CENT = Decimal('0.01')

def snapshot(sale):
    result = {field:str(getattr(sale,field)) for field in EDIT_FIELDS}
    result.update(status=sale.status, revision=sale.revision, items=[{'product':i.product_id,'quantity':str(i.quantity)} for i in sale.items.all()])
    result['extra_costs']=[{'name':e.name,'amount':str(e.amount)} for e in sale.extra_costs.all()]
    return result

def validate(sale, *, partial=False):
    company = Company.objects.get(pk=1)
    if not company.cutover_date <= sale.date <= timezone.localdate():
        raise ValidationError('Data comercial deve estar entre o corte e hoje.')
    if (sale.channel_id or not partial) and not SalesChannel.objects.filter(pk=sale.channel_id,active=True).exists(): raise ValidationError('Selecione um canal ativo antes de confirmar.')
    if (sale.location_id or not partial) and not StockLocation.objects.filter(pk=sale.location_id,active=True).exists(): raise ValidationError('Selecione um estoque ativo antes de confirmar.')
    for field in FINANCIAL_FIELDS: number(getattr(sale,field),CENT,zero=True)
    if sale.discount > sale.products_amount: raise ValidationError('Desconto não pode exceder o valor dos produtos.')
    number(abs(sale.revenue_adjustment), CENT, zero=True)
    if sale.revenue < 0: raise ValidationError('Receita operacional não pode ser negativa.')
    if sale.tax_override is not None:
        number(sale.tax_override,CENT,zero=True)
        if not sale.tax_reason.strip(): raise ValidationError('Informe o motivo do imposto manual, inclusive para isenção ou valor zero.')
    elif not sale.tax_rule_id: raise ValidationError('Selecione uma regra tributária ou informe imposto manual e motivo.')
    if sale.tax_rule_id:
        rule=TaxRule.objects.get(pk=sale.tax_rule_id)
        if not rule.active or sale.date < rule.starts_on or (rule.ends_on and sale.date > rule.ends_on):
            raise ValidationError('Regra tributária inativa ou fora da vigência na data comercial.')
    return company

@transaction.atomic
def save_draft(*,actor,key,data,items,sale_id=None,revision=0,extra_costs=None):
    require(actor,'core.operate_sales')
    domain_lock()
    data = dict(data)
    data.setdefault('revenue_adjustment', Decimal('0'))
    data.setdefault('revenue_adjustment_reason', '')
    if actor.is_superuser:
        for field in FINANCIAL_FIELDS: data.setdefault(field, Decimal('0'))
        for field in ['invoice_number', 'invoice_series', 'tax_reason', 'notes']: data.setdefault(field, '')
        for field in ['channel', 'location', 'tax_rule', 'tax_override']: data.setdefault(field, None)
        data['date'] = data.get('date') or timezone.localdate()
        if data['tax_override'] is None and not data['tax_rule']: data['tax_override'] = Decimal('0')
        if data['tax_override'] is not None and not data['tax_reason'].strip(): data['tax_reason'] = 'Imposto manual definido pelo master.'
    extra_costs=extra_costs or []
    if len(extra_costs)>100:raise ValidationError("Limite de 100 taxas extras por venda.")
    for name,amount in extra_costs:
        if not name.strip() or len(name)>120:raise ValidationError("Informe a descrição da taxa extra.")
        number(amount,CENT,zero=True)
    key=UUID(str(key))
    fingerprint=_fingerprint([actor.pk,{k:str(v.pk if hasattr(v,'pk') else v) for k,v in data.items()},items,extra_costs])
    if sale_id is None:
        previous=Sale.objects.filter(key=key).first()
        if previous:
            if previous.creation_fingerprint!=fingerprint: raise ValidationError('Envio já utilizado com outros dados.')
            return previous
        sale=Sale(key=key,creation_fingerprint=fingerprint,created_by=actor)
        before={}
    else:
        sale=Sale.objects.select_for_update().get(pk=sale_id)
        if sale.status!='DRAFT': raise ValidationError('Somente rascunhos podem ser editados.')
        if sale.revision!=revision: raise ValidationError('A venda mudou em outra sessão. Reabra a edição.')
        before=snapshot(sale)
    if (not items and not actor.is_superuser) or len(items)>100: raise ValidationError('Informe de 1 a 100 itens.')
    if (data['revenue_adjustment'] != sale.revenue_adjustment or data['revenue_adjustment_reason'] != sale.revenue_adjustment_reason) and not actor.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if data['revenue_adjustment'] and not data['revenue_adjustment_reason'].strip():
        data['revenue_adjustment_reason'] = 'Ajuste gerencial definido pelo master.'
    products={p.pk:p for p in Product.objects.filter(pk__in=[i[0] for i in items],active=True)}
    for pid,quantity in items:
        number(quantity,QTY)
        if pid not in products: raise ValidationError('Produto inexistente ou inativo.')
    for field in EDIT_FIELDS: setattr(sale,field,data[field])
    sale.invoice_number=sale.invoice_number.strip().upper()
    sale.invoice_series=sale.invoice_series.strip().upper()
    if not sale.invoice_number: sale.invoice_series = ''
    # Normalize numeric NF/series so leading zeroes do not bypass duplicate checks.
    for field in ['invoice_number','invoice_series']:
        value=getattr(sale,field)
        if value.isdecimal():setattr(sale,field,str(int(value)))
    sale.extra_costs_total=sum((amount for _,amount in extra_costs),Decimal("0"))
    validate(sale, partial=actor.is_superuser)
    sale.revision+=1
    sale.full_clean(exclude=['stock_operation','return_operation','confirmed_by','cancelled_by','confirmed_at','cancelled_at','tax_snapshot'])
    sale.save()
    sale.extra_costs.all().delete()
    for name,amount in extra_costs:SaleExtraCost.objects.create(sale=sale,name=name.strip(),amount=amount)
    sale.items.all().delete()
    for pid,quantity in items: SaleItem.objects.create(sale=sale,product_id=pid,quantity=quantity)
    audit(actor,sale,'save_sale_draft',before,snapshot(sale))
    return sale

@transaction.atomic
def confirm(*,actor,sale_id,revision):
    require(actor,'core.confirm_sales')
    require(actor,'core.operate_sales')
    domain_lock()
    sale=Sale.objects.select_for_update().get(pk=sale_id)
    if sale.status=='CONFIRMED': return sale
    if sale.status!='DRAFT': raise ValidationError('Venda cancelada não pode ser confirmada.')
    if sale.revision!=revision: raise ValidationError('A venda foi alterada. Revise os dados antes de confirmar.')
    company=validate(sale)
    items=list(sale.items.select_related('product'))
    if not items: raise ValidationError('Venda sem itens.')
    expanded=[]
    for item in items:
        if not item.product.active: raise ValidationError('Produto inativo.')
        if item.product.kind=='KIT':
            parts=list(item.product.components.all())
            if not parts: raise ValidationError('Kit sem componentes.')
            expanded.append((item,[(p.component_id,number(p.quantity*item.quantity,QTY)) for p in parts]))
        else:expanded.append((item,[(item.product_id,item.quantity)]))
    ids={pid for _,parts in expanded for pid,_ in parts}
    products={p.pk:p for p in Product.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
    if any(not p.active or p.kind!='SIMPLE' for p in products.values()):raise ValidationError('Componente inativo ou kit aninhado.')
    today=timezone.localdate();_date(today,products.values())
    operation=StockOperation.objects.create(kind='SALE_OUT',date=today,actor=actor,reason=sale.reference,fingerprint=_fingerprint(['sale',sale.pk]))
    cmv=Decimal('0')
    for item,parts in expanded:
        item.cmv=Decimal('0')
        for pid,quantity in parts:
            product=products[pid];value=_value_out(product,quantity)
            movement=_apply(operation,product,sale.location,-quantity,-value)
            SaleConsumption.objects.create(item=item,movement=movement)
            item.cmv+=value
        item.unit_cost=quant(item.cmv/item.quantity)
        item.sku_snapshot=item.product.sku;item.name_snapshot=item.product.name
        item.full_clean();item.save();cmv+=item.cmv
    from .taxes import calculate_tax
    sale.tax_amount,sale.tax_snapshot=calculate_tax(sale)
    sale.cmv=cmv;sale.minimum_margin=company.minimum_margin
    sale.status='CONFIRMED';sale.stock_operation=operation;sale.confirmed_by=actor;sale.confirmed_at=timezone.now();sale.revision+=1
    sale.save()
    from apps.finance.services import create_sale_title
    create_sale_title(sale,actor)
    audit(actor,sale,'confirm_sale',{'status':'DRAFT'},{'status':sale.status,'cmv':str(cmv),'tax':sale.tax_snapshot,'tax_amount':str(sale.tax_amount),'stock_operation':operation.pk})
    return sale

@transaction.atomic
def cancel(*,actor,sale_id,reason):
    require(actor,'core.cancel_sales')
    require(actor,'core.operate_sales')
    if not reason.strip() or len(reason)>500: raise ValidationError('Informe o motivo do cancelamento (até 500 caracteres).')
    domain_lock()
    sale=Sale.objects.select_for_update().get(pk=sale_id)
    if sale.status=='CANCELLED':return sale
    from apps.finance.services import cancel_origin
    cancel_origin(actor,reason,sale=sale)
    previous=sale.status
    if previous=='CONFIRMED':
        moves=list(sale.stock_operation.movements.select_related('location').order_by('pk'))
        products={p.pk:p for p in Product.objects.select_for_update().filter(pk__in=[m.product_id for m in moves]).order_by('pk')}
        today=timezone.localdate();_date(today,products.values())
        operation=StockOperation.objects.create(kind='SALE_RETURN',date=today,actor=actor,reason=reason.strip(),fingerprint=_fingerprint(['cancel_sale',sale.pk]),reversal_of=sale.stock_operation)
        for movement in moves:
            _apply(operation,products[movement.product_id],movement.location,-movement.quantity,-movement.value,unit_cost=movement.unit_cost)
        sale.return_operation=operation
    sale.status='CANCELLED';sale.cancelled_by=actor;sale.cancelled_at=timezone.now();sale.cancellation_reason=reason.strip();sale.revision+=1;sale.save()
    audit(actor,sale,'cancel_sale',{'status':previous},{'status':sale.status,'reason':reason,'stock_operation':sale.return_operation_id})
    return sale

@transaction.atomic
def save_configuration(*,actor,model,data,pk=None):
    require(actor,'core.manage_channels' if model is SalesChannel else 'core.manage_taxes');domain_lock()
    obj=model.objects.select_for_update().get(pk=pk) if pk else model()
    before={k:str(getattr(obj,k)) for k in data}
    if model is TaxRule and pk and any(k in data and data[k]!=getattr(obj,k) for k in ['rate','base','starts_on']):
        raise ValidationError('Use Alíquota e vigência para alterar a tributação com histórico.')
    for k,v in data.items():setattr(obj,k,v)
    obj.full_clean();obj.save()
    audit(actor,obj,'sales_configuration',before,{k:str(v) for k,v in data.items()})
    return obj
