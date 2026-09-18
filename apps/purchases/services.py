"""Acquisition, obligations and physical receipt are separate atomic transitions."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from uuid import UUID
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.core.models import Company
from apps.core.services import require, audit
from apps.products.models import Product
from apps.inventory.models import StockLocation, StockOperation
from apps.inventory.services import domain_lock, number, QTY, MONEY, quant, _fingerprint, _date, _apply
from .models import Supplier, Purchase, PurchaseItem, PurchaseInstallment

CENT=Decimal('0.01')
FIELDS=['supplier','document','series','date','location','discount','freight','other_costs','notes']

def normalized_document(value):
    value=value.strip().upper()
    return str(int(value)) if value.isdecimal() else value

def allocation(subtotals,total):
    """Largest remainder allocation in cents: nonnegative and exactly conservative."""
    basis=sum(subtotals,Decimal('0'))
    if basis==0:
        if total:raise ValidationError('Não é possível ratear custos sobre itens com valor total zero.')
        return [Decimal('0.00') for _ in subtotals]
    cents=total/CENT
    exact=[cents*value/basis for value in subtotals]
    whole=[value.to_integral_value(rounding=ROUND_FLOOR) for value in exact]
    remaining=int(cents-sum(whole))
    order=sorted(range(len(subtotals)),key=lambda i:(-(exact[i]-whole[i]),i))
    for i in order[:remaining]:whole[i]+=1
    return [value*CENT for value in whole]

def snapshot(purchase):
    return {**{field:str(getattr(purchase,field)) for field in FIELDS},'status':purchase.status,'total':str(purchase.total),'revision':purchase.revision,'items':list(purchase.items.values('product_id','sku_snapshot','name_snapshot')),'quantities_costs':[(str(i.quantity),str(i.unit_cost),str(i.allocated_total)) for i in purchase.items.all()],'installments':[(i.number,str(i.due_date),str(i.amount),i.notes) for i in purchase.installments.all()]}

def validate_active(purchase):
    if not Supplier.objects.filter(pk=purchase.supplier_id,active=True).exists():raise ValidationError('Fornecedor inativo.')
    if not StockLocation.objects.filter(pk=purchase.location_id,active=True).exists():raise ValidationError('Estoque de destino inativo.')
    if not Company.objects.get(pk=1).cutover_date<=purchase.date<=timezone.localdate():raise ValidationError('Data da compra deve estar entre o corte e hoje.')

def validate_schedule(purchase):
    installments=list(purchase.installments.all())
    if sum((i.amount for i in installments),Decimal('0'))!=purchase.total:raise ValidationError('A soma das parcelas deve ser igual ao total da compra.')
    if any(i.due_date<purchase.date for i in installments):raise ValidationError('Vencimento não pode ser anterior à compra.')

@transaction.atomic
def save_supplier(*,actor,data,pk=None):
    require(actor,'core.manage_suppliers')
    require(actor,'core.operate_purchases');domain_lock()
    obj=Supplier.objects.select_for_update().get(pk=pk) if pk else Supplier()
    before={k:str(getattr(obj,k)) for k in data}
    allowed={'legal_name','trade_name','document','contact','phone','email','notes','active'}
    if set(data)-allowed:raise ValidationError('Campo de fornecedor inválido.')
    for key,value in data.items():setattr(obj,key,value)
    obj.document=''.join(c for c in obj.document if c not in './- ')
    if obj.document and (not obj.document.isascii() or not obj.document.isdecimal() or len(obj.document) not in {11,14}):raise ValidationError('Informe CPF com 11 ou CNPJ com 14 dígitos, ou deixe vazio.')
    obj.full_clean();obj.save();audit(actor,obj,'save_supplier',before,{k:str(getattr(obj,k)) for k in allowed})
    return obj

@transaction.atomic
def save_draft(*,actor,key,data,items,installments,purchase_id=None,revision=0):
    require(actor,'core.operate_purchases');domain_lock()
    try:key=UUID(str(key))
    except (ValueError,TypeError):raise ValidationError('Identificador de envio inválido.')
    fingerprint=_fingerprint([actor.pk,{k:str(v.pk if hasattr(v,'pk') else v) for k,v in data.items()},items,installments])
    if purchase_id is None:
        existing=Purchase.objects.filter(key=key).first()
        if existing:
            if existing.fingerprint!=fingerprint:raise ValidationError('Envio já utilizado com outros dados.')
            return existing
        purchase=Purchase(key=key,fingerprint=fingerprint,created_by=actor);before={}
    else:
        purchase=Purchase.objects.select_for_update().get(pk=purchase_id)
        if purchase.status!='DRAFT':raise ValidationError('Somente rascunhos podem ser editados.')
        if purchase.revision!=revision:raise ValidationError('A compra mudou em outra sessão. Reabra a edição.')
        before=snapshot(purchase)
    if not items or len(items)>100 or len(installments)>120:raise ValidationError('Informe de 1 a 100 itens e no máximo 120 parcelas.')
    for field in FIELDS:setattr(purchase,field,data[field])
    purchase.document=normalized_document(purchase.document);purchase.series=normalized_document(purchase.series)
    validate_active(purchase)
    for field in ['discount','freight','other_costs']:number(getattr(purchase,field),CENT,zero=True)
    products={p.pk:p for p in Product.objects.filter(pk__in=[i[0] for i in items],active=True,kind='SIMPLE')}
    subtotals=[]
    for pid,qty,cost in items:
        number(qty,QTY);number(cost,MONEY,zero=True)
        if pid not in products:raise ValidationError('Compra exige produtos simples ativos. Kits virtuais não são recebidos.')
        subtotals.append((qty*cost).quantize(CENT,rounding=ROUND_HALF_UP))
    purchase.products_total=sum(subtotals,Decimal('0'))
    if purchase.discount>purchase.products_total:raise ValidationError('Desconto não pode exceder o total dos produtos.')
    purchase.total=purchase.products_total-purchase.discount+purchase.freight+purchase.other_costs
    allocated=allocation(subtotals,purchase.total)
    for due,amount,notes in installments:
        number(amount,CENT)
        if due<purchase.date:raise ValidationError('Vencimento anterior à compra.')
        if len(notes)>500:raise ValidationError('Observação da parcela excede 500 caracteres.')
    # Optional in draft; confirmation requires full and exact schedule.
    if installments and sum((i[1] for i in installments),Decimal('0'))!=purchase.total:raise ValidationError('A soma das parcelas deve ser igual ao total da compra.')
    purchase.revision+=1
    purchase.full_clean(exclude=['received_date','receipt','reversal','confirmed_by','received_by','cancelled_by','confirmed_at','received_at','cancelled_at'])
    purchase.save();purchase.items.all().delete();purchase.installments.all().delete()
    for (pid,qty,cost),subtotal,value in zip(items,subtotals,allocated):
        p=products[pid]
        PurchaseItem.objects.create(purchase=purchase,product=p,quantity=qty,unit_cost=cost,subtotal=subtotal,allocated_total=value,landed_unit_cost=quant(value/qty),sku_snapshot=p.sku,name_snapshot=p.name)
    for index,(due,amount,notes) in enumerate(installments,1):PurchaseInstallment.objects.create(purchase=purchase,number=index,due_date=due,amount=amount,notes=notes)
    audit(actor,purchase,'save_purchase_draft',before,snapshot(purchase));return purchase

@transaction.atomic
def confirm(*,actor,purchase_id,revision):
    require(actor,'core.confirm_purchases')
    require(actor,'core.operate_purchases');domain_lock()
    p=Purchase.objects.select_for_update().get(pk=purchase_id)
    if p.status in {'ORDERED','RECEIVED'}:return p
    if p.status!='DRAFT':raise ValidationError('Compra cancelada não pode ser confirmada.')
    if p.revision!=revision:raise ValidationError('A compra mudou. Revise antes de confirmar.')
    validate_active(p);validate_schedule(p)
    if not p.items.exists():raise ValidationError('Compra sem itens.')
    if p.items.filter(product__active=False).exists():raise ValidationError('Produto inativo.')
    p.status='ORDERED';p.confirmed_by=actor;p.confirmed_at=timezone.now();p.revision+=1;p.save()
    from apps.finance.services import create_purchase_titles
    create_purchase_titles(p,actor)
    audit(actor,p,'confirm_purchase',{'status':'DRAFT'},{'status':p.status,'total':str(p.total),'installments':p.installments.count()});return p

@transaction.atomic
def receive(*,actor,purchase_id,date,revision):
    require(actor,'core.receive_purchases')
    require(actor,'core.operate_purchases');domain_lock()
    p=Purchase.objects.select_for_update().get(pk=purchase_id)
    if p.status=='RECEIVED':return p
    if p.status!='ORDERED':raise ValidationError('Confirme a compra antes de receber.')
    if p.revision!=revision:raise ValidationError('A compra mudou. Revise antes de receber.')
    validate_active(p);validate_schedule(p)
    if date<p.date:raise ValidationError('Recebimento não pode ser anterior à compra.')
    items=list(p.items.order_by('product_id','pk'))
    products={product.pk:product for product in Product.objects.select_for_update().filter(pk__in=[i.product_id for i in items]).order_by('pk')}
    if not items or any(not product.active or product.kind!='SIMPLE' for product in products.values()):raise ValidationError('Itens inválidos ou inativos.')
    _date(date,products.values())
    op=StockOperation.objects.create(kind='PUR_RECEIPT',date=date,actor=actor,reason=f'Compra {p.document}/{p.series}',fingerprint=_fingerprint(['purchase',p.pk]))
    for item in items:
        item.movement=_apply(op,products[item.product_id],p.location,item.quantity,item.allocated_total,unit_cost=item.landed_unit_cost)
        item.save(update_fields=['movement'])
    p.status='RECEIVED';p.receipt=op;p.received_by=actor;p.received_at=timezone.now();p.received_date=date;p.revision+=1;p.save()
    audit(actor,p,'receive_purchase',{'status':'ORDERED'},{'status':p.status,'operation':op.pk,'date':str(date),'total':str(p.total)})
    return p

@transaction.atomic
def cancel(*,actor,purchase_id,reason):
    require(actor,'core.cancel_purchases')
    require(actor,'core.operate_purchases')
    if not reason.strip() or len(reason)>500:raise ValidationError('Informe motivo de até 500 caracteres.')
    domain_lock();p=Purchase.objects.select_for_update().get(pk=purchase_id)
    if p.status=='CANCELLED':return p
    from apps.finance.services import cancel_origin
    cancel_origin(actor,reason,purchase_installment__purchase=p)
    previous=p.status
    if previous=='RECEIVED':
        moves=list(p.receipt.movements.select_related('location').order_by('-pk'))
        products={product.pk:product for product in Product.objects.select_for_update().filter(pk__in=[m.product_id for m in moves]).order_by('pk')}
        for product in products.values():
            latest=product.movements.filter(operation__reversal__isnull=True).exclude(operation__kind='REVERSAL').order_by('-pk').first()
            if latest.operation_id!=p.receipt_id:raise ValidationError('Há movimentos posteriores nos produtos. Não é seguro desfazer este recebimento. Regularize as operações posteriores antes do cancelamento.')
        today=timezone.localdate();_date(today,products.values())
        op=StockOperation.objects.create(kind='PUR_RETURN',date=today,actor=actor,reason=reason,fingerprint=_fingerprint(['cancel_purchase',p.pk]),reversal_of=p.receipt)
        for move in moves:_apply(op,products[move.product_id],move.location,-move.quantity,-move.value,average_override=move.before_average,unit_cost=move.unit_cost)
        p.reversal=op
    # Payment services in Phase 5 must block/reverse settled installments first.
    p.installments.update(status='CANCELLED')
    p.status='CANCELLED';p.cancelled_by=actor;p.cancelled_at=timezone.now();p.cancellation_reason=reason;p.revision+=1;p.save()
    audit(actor,p,'cancel_purchase',{'status':previous},{'status':p.status,'reason':reason,'reversal':p.reversal_id});return p
