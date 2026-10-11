"""Dated stock snapshots reconcile the ledger without rewriting later movements."""
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, Max
from django.utils import timezone
from apps.accounts.access import master
from apps.core.services import audit
from apps.products.models import Product
from apps.products.services import save_product
from .models import StockLocation, StockBalance, StockMovement, StockOperation, InventoryReconciliation
from .services import domain_lock, number, QTY, MONEY, quant, _apply, _date


def parse_snapshot(raw):
    if len(raw) > 2_000_000:
        raise ValidationError('Arquivo excede 2 MB.')
    try:
        data = json.loads(raw)
        if data['version'] != 2 or not data['locations']:
            raise ValueError()
        day = date.fromisoformat(data['date'])
        names = set()
        rows = []
        for source in data['locations']:
            name = source['location'].strip()
            if not name or len(name) > 120 or name in names or not isinstance(source['complete'], bool):
                raise ValueError()
            names.add(name)
            items = []
            skus = set()
            for item in source['items']:
                sku = item['sku'].strip()
                if not sku or sku in skus:
                    raise ValueError()
                skus.add(sku)
                qty = number(Decimal(item['quantity']), QTY, zero=True)
                cost = number(Decimal(item['cost']), MONEY, zero=True)
                value = number(Decimal(item['value']), MONEY, zero=True)
                if (not qty and value) or (qty and abs(quant(qty * cost) - value) > max(MONEY, qty * MONEY)):
                    raise ValidationError(f'{sku}: quantidade, custo e valor incompatíveis.')
                product = dict(sku=sku, name=item['name'].strip(), unit=item.get('unit', 'UN').strip())
                Product(**product).full_clean(validate_unique=False, validate_constraints=False)
                items.append(dict(product, quantity=str(qty), cost=str(cost), value=str(value)))
            if not items:
                raise ValueError()
            rows.append(dict(location=name, complete=source['complete'], items=sorted(items, key=lambda r:r['sku'])))
        payload = dict(version=2, date=str(day), locations=sorted(rows,key=lambda r:r['location']))
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return day, payload, digest
    except (KeyError, ValueError, TypeError, AttributeError, InvalidOperation) as exc:
        raise ValidationError('Arquivo de conciliação inválido. Confira SKU, depósitos, data e decimais.') from exc


def revision():
    # Capture projection/catalog state as well as the immutable ledger watermark.
    content = [StockMovement.objects.aggregate(last=Max('pk'))['last'],
               list(Product.objects.order_by('pk').values_list('pk','sku','active','kind','unit')),
               list(StockBalance.objects.order_by('pk').values_list('product_id','location_id','quantity','value','average_cost'))]
    return hashlib.sha256(json.dumps(content, default=str).encode()).hexdigest()


@transaction.atomic
def reconcile(*, actor, raw, commit=False, expected_revision=None):
    master(actor)
    day, payload, digest = parse_snapshot(raw)
    domain_lock()
    previous = InventoryReconciliation.objects.filter(digest=digest).first()
    if previous:
        return dict(previous.report, already_applied=True)
    if InventoryReconciliation.objects.filter(base_date=day).exists():
        raise ValidationError('Esta data-base já foi conciliada com outro arquivo. Não reaplique: registre uma nova contagem com data-base atual.')
    _date(day, [])
    current_revision = revision()
    if commit and expected_revision != current_revision:
        raise ValidationError('O estoque mudou desde a prévia. Confira novamente antes de aplicar.')
    products = {p.sku:p for p in Product.objects.select_for_update().order_by('pk')}
    plan = []
    report = dict(date=str(day), digest=digest, revision=current_revision, committed=False, locations=[], new_products=[], changes=[])
    for source in payload['locations']:
        try:
            location = StockLocation.objects.get(name=source['location'], active=True)
        except StockLocation.DoesNotExist as exc:
            raise ValidationError(f"Depósito ativo não encontrado: {source['location']}. Ajuste o nome no arquivo; nenhum depósito será criado.") from exc
        items = {i['sku']:i for i in source['items']}
        omitted = []
        if source['complete']:
            # A complete snapshot explicitly means absent SKUs have zero at base date.
            for balance in StockBalance.objects.filter(location=location).select_related('product'):
                p = balance.product
                if p.sku not in items:
                    items[p.sku] = dict(sku=p.sku,name=p.name,unit=p.unit,quantity='0',value='0',cost=str(balance.average_cost))
                    omitted.append(p.sku)
        total_q = total_v = Decimal(0)
        for sku, item in sorted(items.items()):
            p = products.get(sku)
            if p and p.kind != 'SIMPLE':
                raise ValidationError(f'{sku}: kit virtual não pode receber saldo físico.')
            qty, value, cost = (Decimal(item[k]) for k in ('quantity','value','cost'))
            total_q += qty; total_v += value
            current = StockBalance.objects.filter(product=p,location=location).first() if p else None
            moves = StockMovement.objects.filter(product=p,location=location,operation__date__gt=day) if p else StockMovement.objects.none()
            later = moves.aggregate(q=Sum('quantity'),v=Sum('value'))
            target_q = qty + (later['q'] or Decimal(0))
            target_v = value + (later['v'] or Decimal(0))
            residual = target_v if target_q == 0 else Decimal(0)
            if not target_q:
                target_v = Decimal(0)  # A exhausted position cannot carry inventory value.
            if target_q * target_v < 0:
                raise ValidationError(f'{sku}: a base e movimentos posteriores geram quantidade/valor de sinais opostos. Confira o custo deste produto antes de conciliar.')
            before_q, before_v = (current.quantity,current.value) if current else (Decimal(0),Decimal(0))
            reference = quant(target_v/target_q) if target_q else cost
            changed = (before_q,before_v,current.average_cost if current else Decimal(0)) != (target_q,target_v,reference)
            if not p and sku not in report['new_products']:
                report['new_products'].append(sku)
            entry = dict(sku=sku, location=location.name, before_quantity=str(before_q), quantity=str(target_q), before_value=str(before_v), value=str(target_v), cost=str(reference), later_movements=moves.count(), exhausted_value_adjustment=str(residual))
            if changed or not p:
                report['changes'].append(entry)
            plan.append((item, location, target_q, target_v, reference, changed))
        report['locations'].append(dict(name=location.name, quantity=str(total_q), value=str(total_v), complete=source['complete'], absent_zeroed=omitted))
    if not commit:
        return report
    for item, location, qty, value, cost, changed in plan:
        p = products.get(item['sku'])
        if p is None:
            p = save_product(actor=actor, data={k:item[k] for k in ('sku','name','unit')})
            products[p.sku] = p
        if not changed:
            continue
        # Refresh after adjustments in the other depot; preserve aggregate projection.
        p.refresh_from_db()
        current = StockBalance.objects.filter(product=p,location=location).first()
        before_q,before_v = (current.quantity,current.value) if current else (Decimal(0),Decimal(0))
        operation = StockOperation.objects.create(key=uuid4(),fingerprint=digest,kind='RECONCILE',date=timezone.localdate(),actor=actor,
            reason=f'Conciliação de posição em {day}; movimentos posteriores preservados. Arquivo {digest[:16]}.')
        _apply(operation,p,location,qty-before_q,value-before_v,unit_cost=cost,local_average_override=cost,average_override=cost)
    report['committed'] = True
    record = InventoryReconciliation.objects.create(base_date=day,digest=digest,actor=actor,report=report)
    audit(actor,record,'inventory_reconciliation',{},report)
    return report
