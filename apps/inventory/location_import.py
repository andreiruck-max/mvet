"""Private JSON inventory snapshot: one initial operation per SKU, many locations."""
import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from apps.core.services import require
from apps.products.models import Product
from apps.products.services import save_product
from .models import OpeningImport, StockLocation, StockOperation
from .services import domain_lock, number, quant, QTY, MONEY, _date, _apply


def read_snapshot(path):
    raw = Path(path).read_bytes()
    if len(raw) > 10_000_000:
        raise ValidationError('Arquivo excede 10 MB.')
    try:
        data = json.loads(raw.decode('utf-8-sig'))
        if data['version'] != 1 or not isinstance(data['products'], list) or not data['products']:
            raise ValueError()
        day = date.fromisoformat(data['date'])
        products = []
        seen = set()
        totals = {}
        for source in data['products']:
            row = {key: source[key].strip() for key in ('sku', 'name', 'unit')}
            if not row['sku'] or row['sku'] in seen:
                raise ValidationError('SKU ausente ou repetido no arquivo.')
            seen.add(row['sku'])
            Product(**row).full_clean(validate_unique=False, validate_constraints=False)
            row['balances'] = []
            locations = set()
            for item in source['balances']:
                location = item['location'].strip()
                if not location or len(location) > 120 or location in locations:
                    raise ValidationError('Depósito ausente, repetido ou com nome longo.')
                locations.add(location)
                qty = number(Decimal(item['quantity']), QTY, zero=True)
                cost = number(Decimal(item['cost']), MONEY, zero=True)
                note = item.get('note', '').strip()
                if len(note) > 250:
                    raise ValidationError('Observação excede 250 caracteres.')
                row['balances'].append(dict(location=location, quantity=qty, cost=cost, note=note))
                total = totals.setdefault(location, dict(rows=0, quantity=Decimal(0), value=Decimal(0)))
                total['rows'] += 1
                total['quantity'] += qty
                total['value'] += quant(qty * cost)
            if not row['balances']:
                raise ValidationError('Produto sem posição de estoque.')
            qty = sum(b['quantity'] for b in row['balances'])
            value = sum(quant(b['quantity'] * b['cost']) for b in row['balances'])
            if not qty and len({b['cost'] for b in row['balances']}) > 1:
                raise ValidationError('Custos de referência divergentes em produto sem saldo.')
            Product(**row_without_balances(row), quantity=qty, value=value,
                    average_cost=quant(value / qty) if qty else row['balances'][0]['cost']).full_clean(
                        validate_unique=False, validate_constraints=False)
            products.append(row)
    except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation) as exc:
        raise ValidationError('Formato inválido: confira versão, data, produtos e decimais com ponto.') from exc
    # Canonical content makes ordering/whitespace irrelevant to replay detection.
    products.sort(key=lambda row: row['sku'])
    for row in products:
        row['balances'].sort(key=lambda item: item['location'])
    digest = hashlib.sha256(json.dumps([str(day), products], sort_keys=True, default=str).encode()).hexdigest()
    report = {'date': str(day), 'products': len(products), 'locations': {
        name: {key: str(value) if isinstance(value, Decimal) else value for key, value in total.items()}
        for name, total in totals.items()}, 'digest': digest, 'committed': False}
    return day, products, report


def row_without_balances(row):
    return {key: row[key] for key in ('sku', 'name', 'unit')}


@transaction.atomic
def load_snapshot(*, actor, path, commit=False):
    for permission in ('operate_stock', 'manage_products', 'receive_stock', 'view_costs'):
        require(actor, 'core.' + permission)
    day, rows, report = read_snapshot(path)
    domain_lock()
    previous = OpeningImport.objects.filter(digest=report['digest']).first()
    if previous:
        return {**previous.report, 'already_loaded': True}
    _date(day, [])
    existing = list(Product.objects.filter(sku__in=[r['sku'] for r in rows]).values_list('sku', flat=True))
    if existing:
        raise ValidationError('SKUs já cadastrados; nenhuma carga aplicada. Concilie antes: ' + ', '.join(existing))
    names = list(report['locations'])
    if StockLocation.objects.filter(name__in=names, active=False).exists():
        raise ValidationError('Um depósito está inativo.')
    if not commit:
        return report
    locations = {name: StockLocation.objects.get_or_create(name=name)[0] for name in sorted(names)}
    for row in rows:
        product = save_product(actor=actor, data={**row_without_balances(row), 'kind': 'SIMPLE'})
        # Only newly created, never-moved products reach this path. Do not backdate
        # a current stock snapshot to the company cutover or replay past sales.
        reason = 'Posição inicial por depósito em ' + str(day)
        notes = [b['note'] for b in row['balances'] if b['note']]
        if notes:
            reason += '. ' + ' / '.join(notes)
        if len(reason) > 500:
            raise ValidationError('Observações excedem o limite do movimento.')
        operation = StockOperation.objects.create(
            key=uuid.uuid5(uuid.NAMESPACE_URL, report['digest'] + ':' + row['sku']),
            fingerprint=report['digest'], kind='OPENING', date=day, actor=actor, reason=reason)
        # Zero reference costs first, so they never override a positive balance's average.
        for item in sorted(row['balances'], key=lambda b: (b['quantity'] != 0, b['location'])):
            _apply(operation, product, locations[item['location']], item['quantity'],
                   quant(item['quantity'] * item['cost']), unit_cost=item['cost'],
                   average_override=item['cost'] if not item['quantity'] and not product.quantity else None)
    report['committed'] = True
    OpeningImport.objects.create(digest=report['digest'], actor=actor, report=report)
    return report
