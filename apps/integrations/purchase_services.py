"""Assisted incoming NF-e import: stage first, create an editable draft only."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.core.services import require, audit
from apps.inventory.services import domain_lock, _fingerprint
from apps.purchases import services as purchases
from apps.products.models import Product
from .models import PurchaseInvoiceImport
from .normalization import normalize, text, decimal_text

CENT=Decimal('0.01')


def parse_ncm_taxes(raw, label):
    """Explicit tax amounts from accounting, keyed by NCM; never infer from NF total."""
    totals={}
    for line in str(raw or '').splitlines():
        line=line.strip()
        if not line:
            continue
        if line.count('=') != 1:
            raise ValidationError(f'{label}: informe uma linha por NCM no formato 85437092=510,82.')
        ncm,amount=(part.strip() for part in line.split('=',1))
        if len(ncm)!=8 or not ncm.isascii() or not ncm.isdecimal() or ncm in totals:
            raise ValidationError(f'{label}: NCM inválido ou repetido: {ncm}.')
        amount=amount.replace('R$', '').replace(' ', '')
        if ',' in amount:
            amount=amount.replace('.', '').replace(',', '.')
        try:
            value=Decimal(decimal_text(amount,2))
        except (InvalidOperation, ValidationError):
            raise ValidationError(f'{label}: valor inválido no NCM {ncm}.') from None
        totals[ncm]=value
    return totals


def allocate_ncm_taxes(items, totals, field):
    """Exact-cent allocation only among matching NCM lines, by net product value."""
    for ncm,amount in totals.items():
        indices=[idx for idx,item in enumerate(items) if item['ncm']==ncm]
        if not indices:
            raise ValidationError(f'{field.upper()}: NCM {ncm} não corresponde a nenhum item da nota.')
        basis=[items[idx]['net_basis'] for idx in indices]
        shares=purchases.allocation(basis,amount)
        for index,share in zip(indices,shares):
            items[index][field]=share


def normalize_purchase(payload, issuer):
    if not isinstance(payload, dict): raise ValidationError('Nota de entrada inválida.')
    key = text(payload.get('chaveAcesso'), 44)
    # Incoming third-party NF-e has the supplier's CNPJ in its access key.
    source = normalize(payload, key[6:20])
    source.pop('customer_name', None)  # Purchases retain their existing supplier projection.
    if source['type'] != '0': raise ValidationError('Somente notas de entrada podem gerar compras.')
    xml=payload.get('_xml_discounts') or {}
    if xml.get('fiscal'):
        source['fiscal']=xml['fiscal']
        source['freight']=xml['fiscal']['vFrete']
        source['other_costs']=str(Decimal(xml['fiscal']['vSeg'])+Decimal(xml['fiscal']['vOutro']))
        for row,fields in zip(source['items'],xml['tax_items']):
            row.update({k:fields[k] for k in ('invoice_st','invoice_other_tax','cfop')})
            row['fiscal_components']=fields
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
    # Do not flag legacy imports as divergent merely by adding empty metadata.
    for local,external,limit in [('supplier_phone','telefone',40),('supplier_email','email',254),('supplier_trade_name','fantasia',240)]:
        value=text(contact.get(external),limit)
        if value:source[local]=value
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


def eligible(source, *, reviewed=False, acquisition_kind='NORMAL'):
    if source['type'] != '0' or source['status'] not in ('5', '7'):
        raise ValidationError('A compra exige nota de entrada autorizada ou registrada no Bling.')
    if source['purpose'] not in ('', '1'):
        raise ValidationError('Nota complementar, ajuste ou devolução não pode gerar nova compra.')
    if acquisition_kind not in ('NORMAL','BONUS'):raise ValidationError('Tipo de entrada inválido.')
    # Original supplier CFOP may be outgoing; do not convert it to incoming silently.
    for row in source['items']:
        if row['type'] != 'P' or Decimal(row['quantity']) <= 0:
            raise ValidationError('Compra exige mercadorias com quantidade positiva.')
        if len(row['cfop']) != 4 or row['cfop'][0] not in '123567' or row['cfop'][1:] not in ({'910'} if acquisition_kind=='BONUS' else {'101','102','111','113','116','117','118','120','122','401','403','405'}):
            raise ValidationError('CFOP incompatível com o tipo de entrada. Para bonificação (x910), selecione Bonificação sem financeiro. Remessas, transferências e devoluções continuam bloqueadas.')


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
def create_draft(*, actor, invoice_id, revision, supplier, location, products, discount, freight, other_costs, installments, reviewed=False, acquisition_kind='NORMAL', treatments=None, supplier_data=None, external_freight=None, account=None, st_by_ncm='', difal_by_ncm='', taxes_reviewed=False):
    require(actor, 'core.operate_purchases'); domain_lock()
    invoice = PurchaseInvoiceImport.objects.select_for_update().get(pk=invoice_id)
    if invoice.purchase_id: return invoice.purchase
    if invoice.rejected: raise ValidationError('Nota rejeitada. Reabra antes de importar.')
    legacy_errors=('Compra exige mercadorias com código e quantidade positiva.','CFOP não identificado como aquisição/venda de mercadoria. Confira remessas, transferências e devoluções.')
    reviewable=invoice.error in legacy_errors or invoice.error.startswith('CFOP incompatível com o tipo de entrada.')
    if invoice.revision != revision or (invoice.error and not reviewable): raise ValidationError('Nota mudou ou possui erro. Reabra a conferência.')
    eligible(invoice.source, reviewed=reviewed,acquisition_kind=acquisition_kind)
    if supplier_data is not None:
        if supplier is not None:raise ValidationError('Selecione fornecedor existente ou cadastre um novo, não ambos.')
        supplier=purchases.save_supplier(actor=actor,data=supplier_data)
    if supplier is None:raise ValidationError('Selecione ou cadastre o fornecedor.')
    supplier.refresh_from_db()
    if invoice.source['supplier_document'] and supplier.document != invoice.source['supplier_document']:
        raise ValidationError('CPF/CNPJ do fornecedor selecionado não corresponde à nota. Corrija o cadastro.')
    source_rows = invoice.source['items']
    if len(products) != len(source_rows): raise ValidationError('Vincule todos os itens da nota.')
    treatments=treatments or [{} for _ in source_rows]
    if len(treatments)!=len(source_rows):raise ValidationError('Confira o tratamento de todos os itens.')
    fiscal=invoice.source.get('fiscal')
    if fiscal and (Decimal(fiscal['difference']) or fiscal['issues']):
        raise ValidationError('Composição fiscal não conciliada. '+purchases.reconciliation_message(Decimal(fiscal['vNF']),Decimal(fiscal['reconstructed']),'Total reconstruído do XML')+' '+' '.join(fiscal['issues']))
    items = []
    st_groups=parse_ncm_taxes(st_by_ncm,'ICMS-ST')
    difal_groups=parse_ncm_taxes(difal_by_ncm,'DIFAL')
    from apps.products.services import save_product
    for product, row, treatment in zip(products, source_rows,treatments):
        mode=treatment.get('mode','STOCK')
        if mode not in ('STOCK','NEW','NONSTOCK'):raise ValidationError('Tratamento do item inválido.')
        if mode=='NEW':
            product=save_product(actor=actor,data=dict(sku=treatment.get('new_sku',''),name=treatment.get('new_name',''),unit=treatment.get('new_unit','UN'),kind='SIMPLE',active=True))
        if mode!='NONSTOCK' and not product:raise ValidationError('Selecione ou cadastre o produto que entrará no estoque.')
        ncm=str(treatment.get('ncm') or row.get('ncm') or '').strip()
        if row.get('ncm') and ncm!=row['ncm']:
            raise ValidationError('NCM diverge do XML validado. Reconsulte o documento.')
        ipi=Decimal(treatment.get('ipi') or 0)
        if 'ipi' in row and ipi!=Decimal(row['ipi']):
            raise ValidationError('IPI diverge do XML validado. Reconsulte o documento.')
        if 'invoice_st' in row and Decimal(treatment.get('invoice_st') or 0)!=Decimal(row['invoice_st']):
            raise ValidationError('ST incluído diverge do XML validado.')
        quantity=Decimal(row['quantity'])
        price=Decimal(row['price'])
        item_discount=Decimal(treatment.get('discount') or 0)
        net_basis=(quantity*price).quantize(CENT,rounding=ROUND_HALF_UP)-item_discount
        if net_basis < 0:
            raise ValidationError('Desconto do item não pode exceder o valor bruto da linha.')
        items.append(dict(product_id=product.pk if product else None,quantity=quantity,unit_cost=price,discount=item_discount,
            ncm=ncm,ipi=ipi,st=Decimal('0'),difal=Decimal('0'),net_basis=net_basis,
            invoice_st=Decimal(treatment.get('invoice_st') or 0),invoice_other_tax=Decimal(row.get('invoice_other_tax','0')),
            recoverable_tax=Decimal(treatment.get('recoverable_tax') or 0),fiscal_components=row.get('fiscal_components',{}),
            moves_stock=mode!='NONSTOCK',name=row['name'],category_id=treatment.get('category').pk if treatment.get('category') else None))
    allocate_ncm_taxes(items,st_groups,'st')
    allocate_ncm_taxes(items,difal_groups,'difal')
    for item in items:
        item.pop('net_basis')
    purchase = purchases.save_draft(actor=actor, key=uuid4(), data=dict(supplier=supplier, location=location, account=account,
        taxes_reviewed=taxes_reviewed,document=invoice.number, series=invoice.series, date=invoice.issued_on, acquisition_kind=acquisition_kind,discount=discount,
        freight=freight, external_freight=external_freight or Decimal(0), other_costs=other_costs, notes='Importada do Bling; conferir parcelas e recebimento.'), items=items, installments=installments)
    # Bonus invoices retain a fiscal document but create no supplier obligation.
    # Normal purchases include IPI in the supplier NF, and exclude separately paid entry ST/DIFAL.
    fiscal_composition=purchase.products_total-purchase.item_discounts-discount+freight+other_costs+sum((i.ipi+i.invoice_st+i.invoice_other_tax for i in purchase.items.all()),Decimal(0))
    if fiscal_composition != Decimal(invoice.source['total']):
        raise ValidationError(purchases.reconciliation_message(Decimal(invoice.source['total']),fiscal_composition,'Total dos itens com descontos e custos'))
    purchase.source='bling';purchase.external_id=invoice.external_id;purchase.save(update_fields=['source','external_id'])
    invoice.purchase = purchase; invoice.approved_source = invoice.source; invoice.revision += 1; invoice.save()
    audit(actor, invoice, 'bling_purchase_draft', after={'purchase': purchase.pk, 'review_method': 'explicit_draft_import','acquisition_kind':acquisition_kind,'items':[{k:str(v) for k,v in i.items()} for i in items]})
    return purchase


@transaction.atomic
def set_rejected(*, actor, invoice_id, revision, rejected):
    require(actor, 'core.operate_purchases'); domain_lock()
    invoice = PurchaseInvoiceImport.objects.select_for_update().get(pk=invoice_id)
    if invoice.purchase_id:
        raise ValidationError('Esta nota já gerou uma compra. Use o cancelamento da compra.')
    if invoice.revision != revision:
        raise ValidationError('Nota mudou. Reabra a página antes de continuar.')
    if invoice.rejected != rejected:
        invoice.rejected = rejected
        invoice.revision += 1
        invoice.save(update_fields=['rejected', 'revision'])
        audit(actor, invoice, 'bling_purchase_reject' if rejected else 'bling_purchase_reopen',
              after={'rejected': rejected})
    return invoice
