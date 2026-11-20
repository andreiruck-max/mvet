"""Acquisition, obligations and physical receipt are separate atomic transitions."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from uuid import UUID
from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.utils import timezone
from apps.core.models import Company
from apps.core.services import require, audit
from apps.products.models import Product
from apps.inventory.models import StockLocation, StockOperation
from apps.inventory.services import domain_lock, number, QTY, MONEY, quant, _fingerprint, _date, _apply, prior_local_average
from .models import Supplier, Purchase, PurchaseItem, PurchaseInstallment

CENT=Decimal('0.01')
FIELDS=['taxes_reviewed','account','acquisition_kind','supplier','document','series','date','location','discount','freight','external_freight','other_costs','notes']

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
    return {**{field:str(getattr(purchase,field)) for field in FIELDS},'status':purchase.status,'total':str(purchase.total),'revision':purchase.revision,'items':list(purchase.items.values('product_id','sku_snapshot','name_snapshot','moves_stock','category_snapshot')),'quantities_costs':[(str(i.quantity),str(i.unit_cost),str(i.allocated_total),str(i.nonstock_total),str(i.discount),i.ncm,str(i.ipi),str(i.st),str(i.difal),str(i.invoice_st),str(i.invoice_other_tax),str(i.recoverable_tax),i.fiscal_components) for i in purchase.items.all()],'installments':[(i.number,str(i.due_date),str(i.amount),i.notes) for i in purchase.installments.all()]}

def validate_active(purchase):
    if not Supplier.objects.filter(pk=purchase.supplier_id,active=True).exists():raise ValidationError('Fornecedor inativo.')
    if not StockLocation.objects.filter(pk=purchase.location_id,active=True).exists():raise ValidationError('Estoque de destino inativo.')
    if not Company.objects.get(pk=1).cutover_date<=purchase.date<=timezone.localdate():raise ValidationError('Data da compra deve estar entre o corte e hoje.')

def reconciliation_message(expected, actual, label='Total das parcelas'):
    from django.utils.formats import number_format
    money=lambda value:number_format(value, decimal_pos=2, force_grouping=True)
    difference=actual-expected
    direction='a mais' if difference>0 else 'a menos'
    return f'{label}: R$ {money(actual)}; total da nota: R$ {money(expected)}. Divergência: R$ {money(abs(difference))} {direction}.'

def validate_schedule(purchase):
    installments=list(purchase.installments.all())
    if sum((i.amount for i in installments),Decimal('0'))!=purchase.total:raise ValidationError(reconciliation_message(purchase.total,sum((i.amount for i in installments),Decimal('0'))))
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
    data = {'taxes_reviewed':purchase.taxes_reviewed,'account':purchase.account,'acquisition_kind':'NORMAL','external_freight':Decimal(purchase.external_freight),**data}
    for field in FIELDS:setattr(purchase,field,data[field])
    if purchase.acquisition_kind not in ('NORMAL','BONUS'):raise ValidationError('Tipo de entrada inválido.')
    purchase.document=normalized_document(purchase.document);purchase.series=normalized_document(purchase.series)
    validate_active(purchase)
    if purchase.account_id and not purchase.account.active:raise ValidationError('Conta prevista inativa.')
    for field in ['discount','freight','external_freight','other_costs']:number(getattr(purchase,field),CENT,zero=True)
    # Legacy callers retain stock movement by default. Extended rows carry explicit treatment.
    items=[dict(product_id=i[0],quantity=i[1],unit_cost=i[2],moves_stock=True) if not isinstance(i,dict) else dict(i) for i in items]
    products={p.pk:p for p in Product.objects.filter(pk__in=[i.get('product_id') for i in items],active=True,kind='SIMPLE')}
    subtotals=[];net_subtotals=[]
    from apps.expenses.models import ChartOfAccount
    from apps.expenses.services import category_path
    for item in items:
        pid,qty,cost=item.get('product_id'),item['quantity'],item['unit_cost']
        stock=item.get('moves_stock',True)
        if not isinstance(stock,bool):raise ValidationError('Tratamento de estoque inválido.')
        item['moves_stock']=stock
        item['category_snapshot']={}
        if stock and item.get('category_id'):raise ValidationError('Categoria de despesa é apenas para itens sem estoque.')
        if not stock:
            require(actor,'core.operate_expenses')
            if not str(item.get('name') or (products[pid].name if pid in products else '')).strip():raise ValidationError('Informe a descrição do item sem estoque.')
            if item.get('category_id'):
                category=ChartOfAccount.objects.filter(pk=item['category_id'],postable=True).exclude(nature__in=['REVENUE','DEPRECIATION','GROUP']).first()
                if not category:raise ValidationError('Categoria inválida para item sem estoque.')
                item['category_snapshot']=category_path(category,expense=False)
        number(qty,QTY);number(cost,MONEY,zero=True)
        if (stock or pid is not None) and pid not in products:raise ValidationError('Compra exige produtos simples ativos. Kits virtuais não são recebidos.')
        subtotal=(qty*cost).quantize(CENT,rounding=ROUND_HALF_UP)
        item['discount']=number(item.get('discount',Decimal('0')),CENT,zero=True)
        item['ncm']=str(item.get('ncm') or '').strip()
        if item['ncm'] and (len(item['ncm'])!=8 or not item['ncm'].isascii() or not item['ncm'].isdecimal()):
            raise ValidationError('NCM do item deve ter 8 dígitos.')
        for tax in ('ipi','st','difal','invoice_st','invoice_other_tax','recoverable_tax'):
            item[tax]=number(item.get(tax,Decimal('0')),CENT,zero=True)
        if item['discount']>subtotal:raise ValidationError('Desconto do item não pode exceder seu subtotal.')
        subtotals.append(subtotal)
        net_subtotals.append(subtotal-item['discount'])
    purchase.products_total=sum(subtotals,Decimal('0'))
    net_total=sum(net_subtotals,Decimal('0'))
    if purchase.discount>net_total:raise ValidationError('Desconto geral não pode exceder o total após os descontos dos itens.')
    ipi_total=sum((item['ipi']+item['invoice_st']+item['invoice_other_tax'] for item in items),Decimal('0.00'))
    purchase.total=net_total-purchase.discount+purchase.freight+purchase.other_costs+ipi_total
    if purchase.acquisition_kind=='BONUS':
        if purchase.discount or purchase.freight or purchase.external_freight or purchase.other_costs or installments or any(i[tax] for i in items for tax in ('st','difal','recoverable_tax')):raise ValidationError('Bonificação não gera parcelas nem custos pagos. Registre custos cobrados separadamente.')
        if any(not i['moves_stock'] for i in items):raise ValidationError('Bonificação exige itens destinados ao estoque.')
        purchase.total=Decimal('0.00')
    # The supplier invoice includes IPI; ST/DIFAL assessed on entry are separate obligations.
    # Allocate only general invoice charges; keep each line's IPI/ST/DIFAL on that same SKU.
    direct=[sum((Decimal(i.get('fiscal_components',{}).get(k,'0')) for k in ('freight','insurance','other')),Decimal(0)) for i in items]
    direct_total=sum(direct,Decimal(0))
    if direct_total>purchase.freight+purchase.other_costs:
        raise ValidationError('Frete/seguro/despesas da NF não podem ser menores que os componentes por item do XML.')
    allocated=allocation(net_subtotals,net_total-purchase.discount+purchase.freight+purchase.other_costs-direct_total)
    allocated=[value+charge for value,charge in zip(allocated,direct)]
    allocated=[value+item['ipi']+item['invoice_st']+item['invoice_other_tax']+item['st']+item['difal']-item['recoverable_tax'] for value,item in zip(allocated,items)]
    if purchase.acquisition_kind=='BONUS':allocated=[Decimal('0.00') for _ in items]
    if any(value<0 for value in allocated):raise ValidationError('Crédito tributário não pode exceder o custo da linha.')
    if purchase.external_freight:
        # Carrier freight increases the inventory value only; never the supplier debt.
        stock_basis=[value if item['moves_stock'] else Decimal('0') for item,value in zip(items,net_subtotals)]
        shares=allocation(stock_basis,purchase.external_freight)
        allocated=[base+share for base,share in zip(allocated,shares)]
    for due,amount,notes in installments:
        number(amount,CENT)
        if due<purchase.date:raise ValidationError('Vencimento anterior à compra.')
        if len(notes)>500:raise ValidationError('Observação da parcela excede 500 caracteres.')
    # Optional in draft; confirmation requires full and exact schedule.
    if installments and sum((i[1] for i in installments),Decimal('0'))!=purchase.total:raise ValidationError(reconciliation_message(purchase.total,sum((i[1] for i in installments),Decimal('0'))))
    if purchase_id and hasattr(purchase,'bling_import') and purchase.acquisition_kind=='NORMAL':
        fiscal_total=Decimal(purchase.bling_import.approved_source['total'])
        if purchase.total!=fiscal_total:raise ValidationError(reconciliation_message(fiscal_total,purchase.total,'Composição fiscal do rascunho'))
    purchase.revision+=1
    purchase.full_clean(exclude=['received_date','receipt','reversal','confirmed_by','received_by','cancelled_by','confirmed_at','received_at','cancelled_at'])
    purchase.save();purchase.items.all().delete();purchase.installments.all().delete()
    for item,subtotal,value in zip(items,subtotals,allocated):
        p=products.get(item.get('product_id'));stock=item['moves_stock'];qty=item['quantity']
        obj=PurchaseItem(purchase=purchase,product=p,quantity=qty,unit_cost=item['unit_cost'],subtotal=subtotal,discount=item['discount'],
            ncm=item['ncm'],ipi=item['ipi'],st=item['st'],difal=item['difal'],invoice_st=item['invoice_st'],invoice_other_tax=item['invoice_other_tax'],recoverable_tax=item['recoverable_tax'],fiscal_components=item.get('fiscal_components',{}),
            moves_stock=stock,allocated_total=value if stock else Decimal('0'),nonstock_total=Decimal('0') if stock else value,
            category_id=item.get('category_id'),category_snapshot=item['category_snapshot'],
            landed_unit_cost=quant(value/qty) if stock else Decimal('0'),sku_snapshot=p.sku if p else '',name_snapshot=p.name if p else item['name'])
        obj.full_clean(exclude=['movement']);obj.save()
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
    if not p.taxes_reviewed and p.items.filter(models.Q(ipi__gt=0)|models.Q(st__gt=0)|models.Q(difal__gt=0)|models.Q(invoice_st__gt=0)|models.Q(invoice_other_tax__gt=0)|models.Q(recoverable_tax__gt=0)).exists():
        raise ValidationError('Revise os tributos e créditos recuperáveis com a contabilidade na edição do rascunho.')
    if not p.items.exists():raise ValidationError('Compra sem itens.')
    if p.items.filter(moves_stock=True,product__active=False).exists():raise ValidationError('Produto inativo.')
    if p.items.filter(moves_stock=False).exists():require(actor,'core.operate_expenses')
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
    items=list(p.items.filter(moves_stock=True).order_by('product_id','pk'))
    products={product.pk:product for product in Product.objects.select_for_update().filter(pk__in=[i.product_id for i in items]).order_by('pk')}
    if not p.items.exists() or any(not product.active or product.kind!='SIMPLE' for product in products.values()):raise ValidationError('Itens inválidos ou inativos.')
    _date(date,products.values())
    op=StockOperation.objects.create(kind='PUR_RECEIPT',date=date,actor=actor,reason=f'Compra {p.document}/{p.series}',fingerprint=_fingerprint(['purchase',p.pk])) if items else None
    for item in items:
        item.movement=_apply(op,products[item.product_id],p.location,item.quantity,item.allocated_total,unit_cost=item.landed_unit_cost)
        item.save(update_fields=['movement'])
    p.status='RECEIVED';p.receipt=op;p.received_by=actor;p.received_at=timezone.now();p.received_date=date;p.revision+=1;p.save()
    audit(actor,p,'receive_purchase',{'status':'ORDERED'},{'status':p.status,'operation':op.pk if op else None,'date':str(date),'total':str(p.total)})
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
    if p.tax_obligations.filter(title__status='OPEN').exists():
        raise ValidationError('Revise e cancele separadamente as obrigações fiscais externas antes de cancelar a compra.')
    previous=p.status
    if previous=='RECEIVED' and p.receipt_id:
        moves=list(p.receipt.movements.select_related('location').order_by('-pk'))
        products={product.pk:product for product in Product.objects.select_for_update().filter(pk__in=[m.product_id for m in moves]).order_by('pk')}
        for product in products.values():
            latest=product.movements.filter(operation__reversal__isnull=True).exclude(operation__kind='REVERSAL').order_by('-pk').first()
            if latest.operation_id!=p.receipt_id:raise ValidationError('Há movimentos posteriores nos produtos. Não é seguro desfazer este recebimento. Regularize as operações posteriores antes do cancelamento.')
        today=timezone.localdate();_date(today,products.values())
        op=StockOperation.objects.create(kind='PUR_RETURN',date=today,actor=actor,reason=reason,fingerprint=_fingerprint(['cancel_purchase',p.pk]),reversal_of=p.receipt)
        for move in moves:_apply(op,products[move.product_id],move.location,-move.quantity,-(move.value+move.cost_variance),variance_override=-move.cost_variance,average_override=move.before_average,unit_cost=move.unit_cost,local_average_override=prior_local_average(move))
        p.reversal=op
    # Payment services in Phase 5 must block/reverse settled installments first.
    p.installments.exclude(status='CANCELLED').update(status='CANCELLED')
    p.status='CANCELLED';p.cancelled_by=actor;p.cancelled_at=timezone.now();p.cancellation_reason=reason;p.revision+=1;p.save()
    audit(actor,p,'cancel_purchase',{'status':previous},{'status':p.status,'reason':reason,'reversal':p.reversal_id});return p

@transaction.atomic
def create_tax_obligation(*,actor,purchase_id,kind,counterparty,due_date,account=None):
    """Explicit fiscal payable; never a supplier installment or bank payment."""
    from uuid import uuid4
    from .models import PurchaseTaxObligation
    from apps.finance.services import create_title
    require(actor,'core.operate_purchases');require(actor,'core.operate_finance')
    require(actor,'core.create_financial_titles');domain_lock()
    purchase=Purchase.objects.select_for_update().get(pk=purchase_id)
    if purchase.status not in ('ORDERED','RECEIVED'):
        raise ValidationError('Confirme a compra antes de registrar a obrigação fiscal.')
    if kind not in ('ST','DIFAL'):raise ValidationError('Tributo inválido.')
    existing=purchase.tax_obligations.filter(kind=kind).first()
    if existing:return existing.title
    if not counterparty.strip():raise ValidationError('Informe o credor fiscal.')
    amount=sum((getattr(i,kind.lower()) for i in purchase.items.all()),Decimal(0))
    if amount<=0:raise ValidationError('Esta compra não possui esse tributo externo.')
    title=create_title(actor=actor,key=uuid4(),source='purchase_tax',data=dict(direction='PAY',
        description=f'{kind} externo · compra {purchase.document}/{purchase.series}',
        counterparty=counterparty,date=purchase.date,due_date=due_date,amount=amount,account=account,
        category='PRINCIPAL',notes='Encargo de aquisição / crédito tributário. Não lançar novamente como despesa.'))
    PurchaseTaxObligation.objects.create(purchase=purchase,kind=kind,title=title)
    audit(actor,purchase,'create_purchase_tax_obligation',{},dict(kind=kind,title=title.pk,amount=str(amount)))
    return title
