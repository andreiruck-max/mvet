"""Explicit master-only recovery of an erroneously cancelled sale (ADR 0028)."""
from collections import defaultdict
from decimal import Decimal
from uuid import UUID
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils import timezone
from apps.core.services import audit, require
from apps.finance.models import FinancialTitle
from apps.inventory.models import StockOperation
from apps.inventory.services import domain_lock, _apply, _date, _fingerprint, number
from apps.products.models import Product
from .models import Sale, SaleRecovery


@transaction.atomic
def recover_sale(*, actor, sale_id, revision, key, fees, reason):
    require(actor, 'core.operate_sales')
    require(actor, 'core.confirm_sales')
    require(actor, 'core.cancel_sales')
    if not actor.is_superuser: raise PermissionDenied
    if not reason.strip() or len(reason)>500: raise ValidationError('Informe o motivo da recuperação (até 500 caracteres).')
    fees=number(fees,Decimal('0.01'),zero=True);key=UUID(str(key));reason=reason.strip()
    domain_lock()
    sale=Sale.objects.select_for_update().get(pk=sale_id)
    previous=SaleRecovery.objects.filter(key=key).first()
    if previous:
        if (previous.sale_id,previous.actor_id,previous.before_revision,previous.after_fees,previous.reason)!=(sale.pk,actor.pk,revision,fees,reason):
            raise ValidationError('Envio já utilizado com outros dados.')
        if sale.status!='CONFIRMED' or sale.revision!=revision+1 or sale.stock_operation_id!=previous.recovery_operation_id:
            raise ValidationError('Esta recuperação já foi executada; a venda mudou depois dela.')
        return sale
    if sale.status!='CANCELLED' or sale.revision!=revision:
        raise ValidationError('A venda mudou. Reabra a página antes de recuperar.')
    if not sale.confirmed_at or not sale.stock_operation_id or not sale.return_operation_id:
        raise ValidationError('Recuperação exige venda anteriormente confirmada e estoque estornado.')
    if FinancialTitle.objects.filter(sale=sale).exists():
        raise ValidationError('Venda com financeiro histórico exige revisão específica; nenhuma alteração foi feita.')
    imported=getattr(sale,'bling_import',None)
    if imported and (imported.discrepancy or imported.source_status!='5'):
        raise ValidationError('Nota com divergência ou situação externa diferente de autorizada. Confira o Bling antes de recuperar.')
    returned=sale.return_operation
    if returned.kind!='SALE_RETURN' or returned.reversal_of_id!=sale.stock_operation_id or StockOperation.objects.filter(reversal_of=returned).exists():
        raise ValidationError('Cadeia de estorno inconsistente ou já recuperada.')
    moves=list(returned.movements.select_related('location').order_by('pk'))
    original=list(sale.stock_operation.movements.all())
    def totals(rows):
        result=defaultdict(lambda:[Decimal('0'),Decimal('0')])
        for row in rows:
            result[(row.product_id,row.location_id)][0]+=row.quantity
            result[(row.product_id,row.location_id)][1]+=row.value+row.cost_variance
        return dict(result)
    if not moves or any(m.quantity<=0 or m.value+m.cost_variance<0 for m in moves) or totals(moves)!={k:[-q,-v] for k,(q,v) in totals(original).items()}:
        raise ValidationError('O estorno não corresponde à saída original.')
    if sum((m.value+m.cost_variance for m in moves),Decimal('0'))!=sale.cmv:
        raise ValidationError('Valor do estorno diverge do CMV histórico.')
    products={p.pk:p for p in Product.objects.select_for_update().filter(pk__in=[m.product_id for m in moves]).order_by('pk')}
    if any(not p.active for p in products.values()) or any(not m.location.active for m in moves):
        raise ValidationError('Produto ou depósito inativo. Confira o cadastro antes de recuperar.')
    today=timezone.localdate();_date(today,products.values())
    operation=StockOperation.objects.create(kind='SALE_OUT',date=today,actor=actor,reason=reason,reversal_of=returned,fingerprint=_fingerprint(['recover_sale',sale.pk,str(key)]))
    for movement in moves:
        _apply(operation,products[movement.product_id],movement.location,-movement.quantity,-(movement.value+movement.cost_variance),unit_cost=movement.unit_cost)
    recovery=SaleRecovery.objects.create(key=key,sale=sale,actor=actor,reason=reason,before_revision=revision,before_fees=sale.fees,after_fees=fees,
        original_operation_id=sale.stock_operation_id,returned_operation=returned,recovery_operation=operation,
        cancellation_snapshot={'actor_id':sale.cancelled_by_id,'at':sale.cancelled_at.isoformat() if sale.cancelled_at else None,'reason':sale.cancellation_reason})
    before={'status':sale.status,'fees':str(sale.fees),'revision':sale.revision,'stock_operation':sale.stock_operation_id,'return_operation':sale.return_operation_id}
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor: cursor.execute("SELECT set_config('mvet.sale_recovery', %s, true)",[str(key)])
    sale.status='CONFIRMED';sale.fees=fees;sale.stock_operation=operation;sale.return_operation=None
    sale.cancelled_by=None;sale.cancelled_at=None;sale.cancellation_reason='';sale.revision+=1
    sale.save(update_fields=['status','fees','stock_operation','return_operation','cancelled_by','cancelled_at','cancellation_reason','revision'])
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor: cursor.execute("SELECT set_config('mvet.sale_recovery', '', true)")
    audit(actor,sale,'recover_cancelled_sale',before,{'status':sale.status,'fees':str(fees),'revision':sale.revision,'recovery_id':recovery.pk,'stock_operation':operation.pk,'reason':reason})
    return sale
