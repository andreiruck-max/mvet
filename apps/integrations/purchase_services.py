"""Assisted incoming NF-e import: stage first, create an editable draft only."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.core.services import require, audit
from apps.inventory.services import domain_lock, _fingerprint
from apps.purchases import services as purchases
from apps.products.models import Product
from .models import PurchaseInvoiceImport
from .normalization import normalize, text, decimal_text
from .services import compatible_units


def normalize_purchase(payload, issuer):
    if not isinstance(payload, dict): raise ValidationError('Nota de entrada inválida.')
    key = text(payload.get('chaveAcesso'), 44)
    # Incoming third-party NF-e has the supplier's CNPJ in its access key.
    source = normalize(payload, key[6:20])
    if source['type'] != '0': raise ValidationError('Somente notas de entrada podem gerar compras.')
    contact = payload.get('contato') or {}
    if not isinstance(contact, dict): raise ValidationError('Fornecedor externo inválido.')
    document = ''.join(c for c in text(contact.get('numeroDocumento'), 30) if c not in './- ')
    if document and (not document.isascii() or not document.isdecimal() or len(document) not in (11, 14)):
        raise ValidationError('Documento do fornecedor inválido.')
    # Self-issued entries may identify the supplier only in contato.
    if key[6:20] != issuer and document and document != key[6:20]:
        raise ValidationError('Fornecedor diverge do emitente da chave fiscal.')
    source['supplier_document'] = document or (key[6:20] if key[6:20] != issuer else '')
    source['supplier_name'] = text(contact.get('nome'), 200)
    parcels = payload.get('parcelas') or []
    if not isinstance(parcels, list) or len(parcels) > 120: raise ValidationError('Parcelas inválidas.')
    source['installments'] = []
    for parcel in parcels:
        try:
            due = date.fromisoformat(str(parcel['data'])[:10])
            amount = decimal_text(parcel['valor'], 2)
        except (KeyError, TypeError, ValueError): raise ValidationError('Parcela externa inválida.')
        source['installments'].append({'date': due.isoformat(), 'amount': amount})
    return source


def eligible(source, *, reviewed=False):
    if source['type'] != '0' or source['status'] not in ('5', '7'):
        raise ValidationError('A compra exige nota de entrada autorizada ou registrada no Bling.')
    if source['purpose'] not in ('', '1'):
        raise ValidationError('Nota complementar, ajuste ou devolução não pode gerar nova compra.')
    if reviewed is not True:
        raise ValidationError('Confira destinatário, finalidade de compra e unidades no documento.')
    # Original supplier CFOP may be outgoing; do not convert it to incoming silently.
    for row in source['items']:
        if row['type'] != 'P' or not row['code'] or not row['unit'] or Decimal(row['quantity']) <= 0:
            raise ValidationError('Compra exige mercadorias com código, unidade e quantidade positiva.')
        if len(row['cfop']) != 4 or row['cfop'][0] not in '123567' or row['cfop'][1:] not in {'101','102','111','113','116','117','118','120','122','401','403','405'}:
            raise ValidationError('CFOP não identificado como aquisição/venda de mercadoria. Confira remessas, transferências e devoluções.')


@transaction.atomic
def stage(*, actor, connection, payload):
    require(actor, 'core.fetch_bling'); require(actor, 'core.operate_purchases'); domain_lock()
    external_id = text(payload.get('id'), 40) if isinstance(payload, dict) else ''
    if not external_id.isascii() or not external_id.isdecimal(): raise ValidationError('Identificador externo inválido.')
    obj = PurchaseInvoiceImport.objects.select_for_update().filter(connection=connection, external_id=external_id).first()
    try:
        source = normalize_purchase(payload, connection.issuer)
    except ValidationError as exc:
        if obj:
            obj.error = '; '.join(exc.messages)[:500]; obj.discrepancy = bool(obj.purchase_id)
            obj.revision += 1; obj.save()
            return obj
        raise
    if obj and obj.access_key != source['key']:
        obj.error = 'Identificador externo retornou outra chave fiscal.'; obj.discrepancy = True
        obj.revision += 1; obj.save(); return obj
    if PurchaseInvoiceImport.objects.filter(access_key=source['key']).exclude(pk=obj.pk if obj else None).exists():
        raise ValidationError('Chave fiscal já consultada com outro identificador.')
    fingerprint = _fingerprint(source)
    if not obj: obj = PurchaseInvoiceImport(connection=connection, external_id=external_id)
    changed = bool(obj.pk and obj.fingerprint != fingerprint)
    if obj.purchase_id and changed: obj.discrepancy = True
    if changed: obj.revision += 1
    obj.source = source; obj.fingerprint = fingerprint; obj.access_key = source['key']
    obj.number = source['number']; obj.series = source['series']; obj.issued_on = date.fromisoformat(source['date'])
    obj.error = ''
    try: eligible(source, reviewed=True)
    except ValidationError as exc: obj.error = '; '.join(exc.messages)[:500]
    obj.save(); audit(actor, obj, 'bling_stage_purchase', after={'changed': changed, 'error': obj.error})
    return obj


@transaction.atomic
def create_draft(*, actor, invoice_id, revision, supplier, location, products, discount, freight, other_costs, installments, reviewed):
    require(actor, 'core.operate_purchases'); domain_lock()
    invoice = PurchaseInvoiceImport.objects.select_for_update().get(pk=invoice_id)
    if invoice.purchase_id: return invoice.purchase
    if invoice.revision != revision or invoice.error: raise ValidationError('Nota mudou ou possui erro. Reabra a conferência.')
    eligible(invoice.source, reviewed=reviewed)
    supplier.refresh_from_db()
    if invoice.source['supplier_document'] and supplier.document != invoice.source['supplier_document']:
        raise ValidationError('CPF/CNPJ do fornecedor selecionado não corresponde à nota. Corrija o cadastro.')
    source_rows = invoice.source['items']
    if len(products) != len(source_rows): raise ValidationError('Vincule todos os itens da nota.')
    items = []
    for product, row in zip(products, source_rows):
        product = Product.objects.get(pk=product.pk)
        if not compatible_units(product.unit, row['unit']): raise ValidationError('Unidade incompatível; conversões de embalagem devem ser tratadas antes da importação.')
        items.append((product.pk, Decimal(row['quantity']), Decimal(row['price'])))
    purchase = purchases.save_draft(actor=actor, key=uuid4(), data=dict(supplier=supplier, location=location,
        document=invoice.number, series=invoice.series, date=invoice.issued_on, discount=discount,
        freight=freight, other_costs=other_costs, notes='Importada do Bling; conferir parcelas e recebimento.'), items=items, installments=installments)
    # Financial composition must reconcile; no hidden inference for discount/tax.
    if purchase.total != Decimal(invoice.source['total']):
        raise ValidationError('Total dos itens, desconto, frete e outros custos não fecha o valor da nota. Confira os valores antes de importar.')
    invoice.purchase = purchase; invoice.approved_source = invoice.source; invoice.revision += 1; invoice.save()
    audit(actor, invoice, 'bling_purchase_draft', after={'purchase': purchase.pk, 'reviewed': True})
    return purchase
