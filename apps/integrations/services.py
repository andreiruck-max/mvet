from datetime import date
from decimal import Decimal
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.core.services import audit, require
from apps.inventory.services import domain_lock, _fingerprint
from apps.products.models import Product
from apps.sales import services as sales
from .models import InvoiceImport, ProductAlias
from .normalization import normalize, eligibility, text


@transaction.atomic
def stage(*, actor, connection, payload):
    require(actor, 'core.fetch_bling')
    domain_lock()
    if not isinstance(payload, dict): raise ValidationError('Detalhe externo inválido.')
    external_id = text(payload.get('id'), 40)
    if not external_id.isascii() or not external_id.isdecimal():
        raise ValidationError('Identificador externo inválido.')
    obj = InvoiceImport.objects.select_for_update().filter(connection=connection, external_id=external_id).first()
    try:
        source = normalize(payload, connection.issuer)
    except ValidationError as exc:
        # Preserve previous trusted fields, but block unconfirmed approval.
        if obj is None:
            obj = InvoiceImport(connection=connection, external_id=external_id, number='', fingerprint='')
        obj.error = '; '.join(exc.messages)[:500]
        obj.discrepancy = bool(obj.sale_id)
        if obj.status != 'IGNORED' and not obj.sale_id: obj.status = 'ERROR'
        obj.revision += 1; obj.save()
        audit(actor, obj, 'bling_invalid_detail', after={'error': obj.error})
        return obj
    other = InvoiceImport.objects.filter(access_key=source['key']).exclude(pk=obj.pk if obj else None).first()
    if other:
        raise ValidationError('Chave fiscal já vinculada a outra entrada. Conferir duplicidade.')
    if obj and obj.access_key and obj.access_key != source['key']:
        obj.error = 'O identificador externo retornou outra chave fiscal. Conferência bloqueada.'
        obj.discrepancy = True; obj.revision += 1
        if not obj.sale_id and obj.status != 'IGNORED': obj.status = 'ERROR'
        obj.save()
        audit(actor, obj, 'bling_identity_conflict', after={'error': obj.error})
        return obj
    fingerprint = _fingerprint(source)
    if obj is None:
        obj = InvoiceImport(connection=connection, external_id=external_id)
    changed = bool(obj.pk and obj.fingerprint != fingerprint)
    obj.source = source; obj.fingerprint = fingerprint
    obj.access_key = source['key']; obj.number = source['number']; obj.series = source['series']
    obj.issued_on = date.fromisoformat(source['date']); obj.source_status = source['status']
    obj.error = ''
    # Missing purpose may enter the review queue, never an automatic sale.
    try: eligibility(source, purpose_reviewed=True)
    except ValidationError as exc: obj.error = '; '.join(exc.messages)[:500]
    if obj.sale_id:
        obj.discrepancy = obj.discrepancy or changed
    elif obj.status != 'IGNORED':
        obj.status = 'ERROR' if obj.error else 'PENDING'
    if changed: obj.revision += 1
    obj.save()
    audit(actor, obj, 'bling_stage', after={'fingerprint': fingerprint, 'status': obj.status, 'changed': changed})
    return obj


def resolve(connection, row):
    alias = ProductAlias.objects.select_related('product').filter(connection=connection, code=row['code'], unit=row['unit']).first()
    product = alias.product if alias else Product.objects.filter(sku=row['code']).first()
    if not product or not product.active or product.unit.strip().upper() != row['unit']:
        return None
    return product


@transaction.atomic
def map_product(*, actor, invoice_id, revision, code, unit, product):
    require(actor, 'core.review_bling'); require(actor, 'core.map_bling_products')
    domain_lock()
    invoice = InvoiceImport.objects.select_for_update().get(pk=invoice_id)
    if invoice.revision != revision or invoice.sale_id:
        raise ValidationError('Nota alterada ou já importada. Reabra a conferência.')
    if not any(r['code'] == code and r['unit'] == unit for r in invoice.source.get('items', [])):
        raise ValidationError('Código não pertence à nota.')
    product = Product.objects.get(pk=product.pk)
    if not code or not unit or not product.active or product.unit.strip().upper() != unit:
        raise ValidationError('Produto inativo ou unidade incompatível. Conversão de unidade não é automática.')
    alias = ProductAlias.objects.filter(connection=invoice.connection, code=code, unit=unit).first()
    if alias and alias.product_id != product.pk:
        raise ValidationError('Código já possui outro vínculo. Revisão do cadastro exige tratamento separado.')
    exact = Product.objects.filter(sku=code).first()
    if exact and exact.pk != product.pk:
        raise ValidationError('Código coincide com outro SKU do MVet. Corrija o cadastro antes de vincular.')
    alias, _ = ProductAlias.objects.get_or_create(connection=invoice.connection, code=code, unit=unit, defaults={'product': product})
    invoice.revision += 1; invoice.save()
    audit(actor, alias, 'bling_map_product', after={'code': code, 'unit': unit, 'product': product.pk})


@transaction.atomic
def approve(*, actor, invoice_id, revision, data, extra_costs, reviewed, purpose_reviewed=False):
    require(actor, 'core.review_bling'); require(actor, 'core.approve_bling')
    require(actor, 'core.operate_sales'); require(actor, 'core.confirm_sales')
    domain_lock()
    invoice = InvoiceImport.objects.select_for_update().get(pk=invoice_id)
    if invoice.sale_id: return invoice.sale
    if invoice.revision != revision or invoice.status != 'PENDING' or not reviewed:
        raise ValidationError('Revise a nota atual e confirme os valores, inclusive os zeros.')
    eligibility(invoice.source, purpose_reviewed=purpose_reviewed)
    items = []
    for row in invoice.source['items']:
        product = resolve(invoice.connection, row)
        if product is None: raise ValidationError('Há produto sem vínculo válido. Relacione o SKU e confira a unidade.')
        items.append((product.pk, Decimal(row['quantity'])))
    # Never trust posted invoice identifiers, quantities or external costs.
    data = dict(data, date=invoice.issued_on, invoice_number=invoice.number, invoice_series=invoice.series)
    sale = sales.save_draft(actor=actor, key=uuid4(), data=data, items=items, extra_costs=extra_costs)
    sale.source = 'bling'; sale.external_id = invoice.external_id
    sale.save(update_fields=['source', 'external_id'])
    sale = sales.confirm(actor=actor, sale_id=sale.pk, revision=sale.revision)
    invoice.sale = sale; invoice.approved_source = invoice.source
    invoice.status = 'IMPORTED'; invoice.revision += 1; invoice.save()
    audit(actor, invoice, 'bling_approve', after={'sale': sale.pk, 'fingerprint': invoice.fingerprint,
        'purpose_missing': not bool(invoice.source.get('purpose')),
        'purpose_reviewed': purpose_reviewed is True})
    return sale


@transaction.atomic
def set_ignored(*, actor, invoice_id, revision, ignored, reason):
    require(actor, 'core.review_bling'); require(actor, 'core.approve_bling')
    domain_lock()
    obj = InvoiceImport.objects.select_for_update().get(pk=invoice_id)
    if obj.sale_id or obj.revision != revision or not reason.strip():
        raise ValidationError('Informe motivo e reabra a nota; importadas não podem ser ignoradas/reabertas.')
    old = obj.status
    obj.status = 'IGNORED' if ignored else ('ERROR' if obj.error else 'PENDING')
    obj.revision += 1; obj.save()
    audit(actor, obj, 'bling_ignore' if ignored else 'bling_reopen', {'status': old}, {'status': obj.status, 'reason': reason[:500]})
