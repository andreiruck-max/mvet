"""Explicit historical cost correction; original stock ledger stays immutable."""
from decimal import Decimal
from uuid import UUID
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from apps.accounts.access import master
from apps.core.services import audit
from apps.inventory.services import domain_lock, number, quant
from .models import Sale, SaleCostRevision


def cost_rows(sale):
    prior = sale.cost_revisions.first()
    if prior:
        return prior.after['items']
    return [dict(id=i.pk, sku=i.sku_snapshot, name=i.name_snapshot,
                 quantity=str(i.quantity), unit_cost=str(i.unit_cost), cmv=str(i.cmv))
            for i in sale.items.all()]


def preview(sale, costs):
    before = cost_rows(sale)
    if not before or set(costs) != {row['id'] for row in before}:
        raise ValidationError('Informe o custo de todos os itens desta venda.')
    after = []
    for row in before:
        cost = number(costs[row['id']], Decimal('.000001'), zero=True)
        # Keep original rounding residuals on unchanged lines.
        total = Decimal(row['cmv']) if cost == Decimal(row['unit_cost']) else quant(Decimal(row['quantity']) * cost)
        if total >= Decimal('1000000000000000000'):
            raise ValidationError('CMV acima do limite permitido.')
        after.append(dict(row, unit_cost=str(cost), cmv=str(total)))
    total = sum((Decimal(row['cmv']) for row in after), Decimal(0))
    if total >= Decimal('1000000000000000000'):
        raise ValidationError('CMV total acima do limite permitido.')
    return {'items': before, 'total': str(sale.effective_cmv)}, {'items': after, 'total': str(total)}


@transaction.atomic
def correct_cost(*, actor, sale_id, revision, key, reason, costs):
    master(actor)
    domain_lock()
    key = UUID(str(key))
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise ValidationError('Informe o motivo da correção (até 500 caracteres).')
    costs = {pk: number(value, Decimal('.000001'), zero=True) for pk, value in costs.items()}
    sale = Sale.objects.select_for_update().get(pk=sale_id)
    prior = SaleCostRevision.objects.filter(key=key).first()
    if prior:
        previous_costs = {row['id']: Decimal(row['unit_cost']) for row in prior.after['items']}
        if (prior.sale_id != sale.pk or prior.actor_id != actor.pk or prior.before_revision != revision
                or prior.reason != reason or previous_costs != costs):
            raise ValidationError('Envio já utilizado com outros dados.')
        if sale.revision != revision + 1 or sale.status != 'CONFIRMED':
            raise ValidationError('Esta correção já foi executada; reabra a venda.')
        return sale
    if sale.status != 'CONFIRMED' or sale.revision != revision:
        raise ValidationError('A venda mudou ou não está confirmada. Reabra a página.')
    before, after = preview(sale, costs)
    if all(Decimal(a['unit_cost']) == Decimal(b['unit_cost']) for a, b in zip(before['items'], after['items'])):
        raise ValidationError('Nenhum custo foi alterado.')
    adjustment = Decimal(after['total']) - sale.cmv
    entry = SaleCostRevision.objects.create(key=key, sale=sale, actor=actor, reason=reason,
        before_revision=revision, before_adjustment=sale.cmv_adjustment, after_adjustment=adjustment,
        before=before, after=after)
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('mvet.sale_cost_revision', %s, true)", [str(key)])
    try:
        sale.cmv_adjustment = adjustment
        sale.revision += 1
        sale.save(update_fields=['cmv_adjustment', 'revision'])
    finally:
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('mvet.sale_cost_revision', '', true)")
    audit(actor, sale, 'correct_sale_cost', before, dict(after, reason=reason, correction_id=entry.pk))
    return sale
