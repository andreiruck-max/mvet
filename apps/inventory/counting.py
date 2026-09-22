"""A physical count posts only the difference, never overwrites stock projections."""
from decimal import Decimal
from uuid import uuid4
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.core.models import AuditLog
from apps.core.services import audit, require
from apps.products.models import Product
from .models import StockBalance, StockLocation, StockMovement
from .services import domain_lock, number, QTY, execute, _fingerprint

SALT = 'mvet.inventory.count.v1'


def count_snapshot(actor, product, location):
    require(actor, 'core.operate_stock'); require(actor, 'core.adjust_stock')
    return signing.dumps({'actor': actor.pk, 'product': product.pk, 'location': location.pk,
                          'last': StockMovement.objects.filter(product=product).order_by('-pk').values_list('pk', flat=True).first(),
                          'key': str(uuid4())}, salt=SALT)


@transaction.atomic
def apply_count(*, actor, product_id, location_id, snapshot, counted, reason):
    require(actor, 'core.operate_stock'); require(actor, 'core.adjust_stock')
    number(counted, QTY, zero=True)
    reason = reason.strip()
    if not reason or len(reason) > 350:
        raise ValidationError('Informe o motivo da contagem (até 350 caracteres).')
    try:
        token = signing.loads(snapshot, salt=SALT, max_age=86400)
    except signing.BadSignature as exc:
        raise ValidationError('Contagem expirada ou inválida. Abra novamente a tela.') from exc
    if (token['actor'], token['product'], token['location']) != (actor.pk, product_id, location_id):
        raise ValidationError('Contagem inválida para este produto, depósito ou usuário.')
    domain_lock()
    fingerprint = _fingerprint([snapshot, counted, reason])
    previous = AuditLog.objects.filter(operation='stock_count', after__count_key=token['key']).first()
    if previous:
        if previous.after['fingerprint'] != fingerprint:
            raise ValidationError('Esta contagem já foi confirmada com outros dados. Abra uma nova contagem.')
        return previous.after
    product = Product.objects.select_for_update().get(pk=product_id)
    location = StockLocation.objects.get(pk=location_id, active=True)
    if product.kind != 'SIMPLE' or not product.active:
        raise ValidationError('Contagem exige produto simples e ativo.')
    last = product.movements.order_by('-pk').values_list('pk', flat=True).first()
    if last != token['last']:
        raise ValidationError('O produto foi movimentado após abrir a contagem. Volte e abra uma nova contagem para conferir o saldo atualizado.')
    balance = StockBalance.objects.filter(product=product, location=location).first()
    before = balance.quantity if balance else Decimal(0)
    difference = counted - before
    operation = None
    if difference:
        if difference > 0 and (balance is None or balance.average_cost == 0):
            raise ValidationError('Acréscimo sem custo de referência: use Movimentar estoque → Ajuste: acréscimo e informe o custo.')
        operation = execute(actor=actor, key=token['key'], kind='ADJUST_IN' if difference > 0 else 'ADJUST_OUT',
                            date=timezone.localdate(), reason=f'Contagem: saldo {before}; contado {counted}. {reason}',
                            product_id=product.pk, location_id=location.pk, quantity=abs(difference),
                            cost=balance.average_cost if difference > 0 else None)
    result = {'count_key': token['key'], 'fingerprint': fingerprint, 'location': location.pk,
              'counted': str(counted), 'difference': str(difference), 'reason': reason,
              'operation': operation.pk if operation else None, 'date': str(timezone.localdate())}
    audit(actor, product, 'stock_count', {'quantity': str(before), 'location': location.pk}, result)
    return result
