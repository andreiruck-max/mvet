"""Explicit, master-only reconciliation. No scheduled synchronization."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4
from urllib.parse import urlencode
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.accounts.access import master
from apps.core.models import Company
from apps.core.services import audit
from apps.products.models import Product
from apps.products.pricing import sale_price, retail_location, configure_fixed_price
from apps.inventory.models import StockBalance, StockLocation
from apps.inventory.counting import count_snapshot, apply_count
from apps.inventory.services import domain_lock
from . import bling
from .models import BlingStockCorrection

SALT = 'bling.stock.comparison.v1'


def decimal(value, places):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or abs(number) >= Decimal('1000000000000'):
            raise ValueError
        rounded = number.quantize(Decimal(places), rounding=ROUND_HALF_UP)
        if abs(rounded) >= Decimal('1000000000000'): raise ValueError
        return rounded
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Valor inválido ou precisão incompatível recebida do Bling.') from None


def identifier(value):
    value = str(value)
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValidationError('Identificador inválido recebido do Bling.')
    return value


def deposits():
    rows = bling.read('/depositos?pagina=1&limite=100&situacao=1').get('data')
    if not isinstance(rows, list): raise ValidationError('Lista de depósitos inválida.')
    return [(identifier(row['id']), str(row['descricao'])) for row in rows if row.get('situacao') == 1]


def remote_products(products):
    params = [('pagina', 1), ('limite', 100), ('criterio', 2)] + [('codigos[]', p.sku) for p in products]
    rows = bling.read('/produtos?' + urlencode(params)).get('data')
    if not isinstance(rows, list) or len(rows) >= 100:
        raise ValidationError('Resposta de produtos incompleta. Refine a busca por SKU.')
    found = {}
    for row in rows:
        if not isinstance(row, dict): raise ValidationError('Produto externo inválido.')
        if str(row.get('codigo', '')) in {p.sku for p in products}:
            found.setdefault(str(row.get('codigo', '')), []).append(row)
    return found


def remote_balances(deposit, ids):
    if not ids: return {}
    params = [('idsProdutos[]', identifier(pk)) for pk in ids]
    rows = bling.read('/estoques/saldos/' + identifier(deposit) + '?' + urlencode(params)).get('data')
    if not isinstance(rows, list): raise ValidationError('Resposta de saldos inválida.')
    result = {}
    for row in rows:
        pk = identifier(row.get('produto', {}).get('id'))
        if pk in result: raise ValidationError('Saldo duplicado recebido do Bling.')
        try:
            result[pk] = str(decimal(row.get('saldoFisicoTotal'), '.0001'))
        except ValidationError:
            result[pk] = None
    return result


def external(row, quantity):
    if row.get('situacao') != 'A' or row.get('formato') != 'S' or row.get('tipo') != 'P':
        raise ValidationError('Somente produtos ativos simples ou variações individuais do Bling podem ser corrigidos.')
    price = decimal(row.get('preco'), '.01')
    if price < 0: raise ValidationError('Preço negativo no Bling.')
    return {'id': identifier(row['id']), 'sku': str(row.get('codigo', '')), 'unit': str(row.get('unidade', '')).strip().upper(),
            'price': str(price), 'quantity': quantity}


def local(product, location):
    balance = StockBalance.objects.filter(product=product, location=location).first()
    retail = retail_location()
    if not retail: raise ValidationError('Configure o depósito da loja para calcular o preço de venda do MVet.')
    retail_balance = StockBalance.objects.filter(product=product, location=retail).first()
    price = sale_price(product, retail_balance.average_cost if retail_balance else Decimal(0), Company.objects.get(pk=1).default_markup)
    return {'sku': product.sku, 'unit': product.unit.strip().upper(), 'price': str(price),
            'quantity': str(balance.quantity if balance else Decimal(0)), 'retail': retail.pk,
            'last': product.movements.order_by('-pk').values_list('pk', flat=True).first()}


def comparison(*, actor, products, location, deposit):
    master(actor)
    found = remote_products(products) if products else {}
    ids = [identifier(v[0]['id']) for v in found.values() if len(v) == 1]
    balances = remote_balances(deposit, ids)
    details = {pk: bling.read('/produtos/' + pk).get('data') for pk in ids}
    result = []
    with transaction.atomic():
        domain_lock()
        for original in products:
            product = Product.objects.get(pk=original.pk)
            item = {'product': product}
            try:
                matches = found.get(product.sku, [])
                if len(matches) != 1:
                    raise ValidationError('SKU não encontrado no Bling.' if not matches else 'SKU duplicado no Bling. Corrija o cadastro antes de comparar.')
                row = matches[0]
                pk = identifier(row['id'])
                if pk not in balances or balances[pk] is None: raise ValidationError('Bling não retornou o saldo deste produto; não será tratado como zero.')
                detail = details[pk]
                if not isinstance(detail, dict) or identifier(detail.get('id')) != pk or detail.get('codigo') != product.sku:
                    raise ValidationError('Detalhe não corresponde ao produto solicitado.')
                remote = external(detail, balances[pk])
                current = local(product, location)
                snapshot = {'actor': actor.pk, 'product': product.pk, 'location': location.pk, 'deposit': deposit,
                            'local': current, 'remote': remote, 'key': str(uuid4())}
                item.update(local=current, remote=remote, token=signing.dumps(snapshot, salt=SALT),
                            price_diff=Decimal(current['price']) != Decimal(remote['price']),
                            stock_diff=Decimal(current['quantity']) != Decimal(remote['quantity']))
            except ValidationError as exc:
                item['error'] = '; '.join(exc.messages)
            result.append(item)
    return result


def decode(actor, token):
    master(actor)
    try: snapshot = signing.loads(token, salt=SALT)
    except signing.BadSignature: raise ValidationError('Comparação expirada. Consulte os valores novamente.') from None
    if snapshot['actor'] != actor.pk: raise ValidationError('Comparação pertence a outro usuário.')
    return snapshot


def check_remote(snapshot):
    product = Product.objects.get(pk=snapshot['product'])
    matches = remote_products([product]).get(product.sku, [])
    if len(matches) != 1 or identifier(matches[0]['id']) != snapshot['remote']['id']:
        raise ValidationError('Vínculo por SKU mudou no Bling. Consulte novamente.')
    data = bling.read('/produtos/' + snapshot['remote']['id']).get('data')
    if not isinstance(data, dict) or identifier(data.get('id')) != snapshot['remote']['id']:
        raise ValidationError('Detalhe do produto inválido.')
    balances = remote_balances(snapshot['deposit'], [snapshot['remote']['id']])
    if snapshot['remote']['id'] not in balances or balances[snapshot['remote']['id']] is None: raise ValidationError('Saldo não retornado pelo Bling.')
    current = external(data, balances[snapshot['remote']['id']])
    expected = snapshot['remote']
    if any(current[k] != expected[k] for k in ('id', 'sku')) or any(Decimal(current[k]) != Decimal(expected[k]) for k in ('price', 'quantity')):
        raise ValidationError('Preço, saldo ou cadastro mudou no Bling. Consulte novamente antes de corrigir.')
    if snapshot['deposit'] not in dict(deposits()): raise ValidationError('Depósito Bling inativo ou indisponível.')


def check_local(snapshot):
    product = Product.objects.select_for_update().get(pk=snapshot['product'])
    location = StockLocation.objects.get(pk=snapshot['location'], active=True)
    if not product.active or product.kind != 'SIMPLE': raise ValidationError('Produto local indisponível.')
    current = local(product, location)
    if {k: v for k, v in current.items() if k != 'unit'} != {k: v for k, v in snapshot['local'].items() if k != 'unit'}: raise ValidationError('Dados do MVet mudaram. Consulte novamente antes de corrigir.')
    return product, location


def apply(*, actor, token, field, direction, reason):
    snapshot = decode(actor, token)
    if field not in ('price', 'quantity') or direction not in ('mvet', 'bling'):
        raise ValidationError('Selecione o campo e o sistema que será corrigido.')
    reason = reason.strip()
    if not reason or len(reason) > 350: raise ValidationError('Informe um motivo de até 350 caracteres.')
    # Commit intent BEFORE any remote write. Never resend an ambiguous request.
    with transaction.atomic():
        domain_lock()
        previous = BlingStockCorrection.objects.filter(key=snapshot['key']).first()
        if previous:
            if (previous.actor_id, previous.field, previous.direction, previous.reason) != (actor.pk, field, direction, reason):
                raise ValidationError('Esta prévia já foi utilizada. Consulte novamente.')
            return previous
        if direction == 'bling' and BlingStockCorrection.objects.filter(product_id=snapshot['product'], direction='bling', status__in=['PENDING', 'UNKNOWN']).exists():
            raise ValidationError('Existe uma tentativa sem resultado confirmado para este produto. Confira e encerre a tentativa no histórico antes de reenviar.')
        product, _ = check_local(snapshot)
        correction = BlingStockCorrection.objects.create(key=snapshot['key'], actor=actor, product=product, snapshot=snapshot, field=field, direction=direction, reason=reason)
        audit(actor, correction, 'bling_correction_requested', after={'field': field, 'destination': direction, 'snapshot': snapshot, 'reason': reason})
    sending = False
    try:
        check_remote(snapshot)
        target = Decimal(snapshot['remote' if direction == 'mvet' else 'local'][field])
        if target < 0: raise ValidationError('Saldo negativo não pode ser aplicado por esta tela. Confira as movimentações.')
        with transaction.atomic():
            domain_lock()
            product, location = check_local(snapshot)
            if direction == 'mvet':
                if field == 'price': configure_fixed_price(actor=actor, product_id=product.pk, price=target)
                else:
                    apply_count(actor=actor, product_id=product.pk, location_id=location.pk,
                                snapshot=count_snapshot(actor, product, location), counted=target, reason='Conferência Bling: ' + reason[:320])
                correction.status = 'DONE'
                correction.finished_at = timezone.now()
                correction.save(update_fields=['status', 'finished_at'])
                audit(actor, correction, 'bling_correction_done', after={'status': 'DONE'})
                return correction
        # No inventory lock during network I/O. Remote systems cannot share a DB transaction.
        sending = True
        if field == 'price':
            bling.read('/produtos/' + snapshot['remote']['id'], method='PATCH', payload={'preco': target})
        else:
            bling.read('/estoques', method='POST', payload={'produto': {'id': int(snapshot['remote']['id'])},
                'deposito': {'id': int(snapshot['deposit'])}, 'operacao': 'B', 'quantidade': target,
                'observacoes': f'MVet {correction.key}: {reason}'})
        if field == 'price':
            verified = bling.read('/produtos/' + snapshot['remote']['id']).get('data', {}).get('preco')
        else: verified = remote_balances(snapshot['deposit'], [snapshot['remote']['id']]).get(snapshot['remote']['id'])
        if decimal(verified, '.01' if field == 'price' else '.0001') != target:
            raise ValidationError('Bling respondeu, mas o valor consultado depois não corresponde ao enviado.')
        correction.status = 'DONE'
    except (ValidationError, Product.DoesNotExist, StockLocation.DoesNotExist) as exc:
        correction.status = 'UNKNOWN' if sending else 'FAILED'
        correction.message = ('; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Produto ou depósito indisponível.')[:500]
    correction.finished_at = timezone.now()
    correction.save(update_fields=['status', 'message', 'finished_at'])
    audit(actor, correction, 'bling_correction_result', after={'status': correction.status, 'message': correction.message})
    return correction


@transaction.atomic
def acknowledge(*, actor, correction_id, reason):
    master(actor)
    reason = reason.strip()
    if not reason or len(reason) > 350: raise ValidationError('Descreva o resultado conferido no Bling.')
    domain_lock()
    item = BlingStockCorrection.objects.select_for_update().get(pk=correction_id)
    if item.status not in ('PENDING', 'UNKNOWN') or item.direction != 'bling':
        raise ValidationError('Esta tentativa não precisa de conferência manual.')
    if item.created_at > timezone.now() - timezone.timedelta(minutes=5):
        raise ValidationError('Aguarde cinco minutos após o envio antes de encerrar a tentativa.')
    item.status = 'REVIEWED'
    item.finished_at = timezone.now()
    item.message = 'Conferido manualmente: ' + reason
    item.save(update_fields=['status', 'finished_at', 'message'])
    audit(actor, item, 'bling_correction_reviewed', after={'reason': reason})
    return item


def catalog(*, actor, query='', page=1, search='name'):
    master(actor)
    if not 1 <= page <= 10000: raise ValidationError('Página inválida.')
    params = [('pagina', page), ('limite', 10), ('criterio', 2), ('tipo', 'PS')]
    if query: params.append(('codigos[]' if search == 'sku' else 'nome', query))
    rows = bling.read('/produtos?' + urlencode(params)).get('data')
    if not isinstance(rows, list) or len(rows) > 10: raise ValidationError('Página de produtos inválida.')
    result = []
    for row in rows:
        pk = identifier(row.get('id'))
        sku = str(row.get('codigo', '')).strip()
        result.append({'id': pk, 'sku': sku, 'name': str(row.get('nome', '')), 'price': decimal(row.get('preco'), '.01'),
                       'exists': Product.objects.filter(sku=sku).exists(), 'valid': bool(sku)})
    return result, len(rows) == 10


def new_product_preview(*, actor, remote_id, location, deposit):
    master(actor)
    remote_id = identifier(remote_id)
    if deposit not in dict(deposits()): raise ValidationError('Selecione um depósito válido do Bling.')
    data = bling.read('/produtos/' + remote_id).get('data')
    if not isinstance(data, dict) or identifier(data.get('id')) != remote_id: raise ValidationError('Produto externo inválido.')
    balances = remote_balances(deposit, [remote_id])
    if remote_id not in balances or balances[remote_id] is None: raise ValidationError('Saldo não informado pelo Bling.')
    source = external(data, balances[remote_id])
    source['name'] = str(data.get('nome', '')).strip()
    if not source['sku'] or not source['unit'] or not source['name']: raise ValidationError('Produto sem SKU, unidade ou descrição.')
    if Product.objects.filter(sku=source['sku']).exists(): raise ValidationError('SKU já cadastrado no MVet, inclusive entre produtos inativos.')
    return signing.dumps({'actor': actor.pk, 'key': str(uuid4()), 'source': source,
                          'location': location.pk, 'deposit': deposit}, salt='bling.new.product')


def decode_new(actor, token):
    master(actor)
    try: data = signing.loads(token, salt='bling.new.product', max_age=1800)
    except signing.BadSignature: raise ValidationError('Prévia expirada. Busque o produto novamente.') from None
    if data['actor'] != actor.pk: raise ValidationError('Prévia pertence a outro usuário.')
    return data


def create_product(*, actor, token, name, price, include_stock, cost, reason):
    from apps.core.models import AuditLog
    from apps.products.services import save_product
    from apps.inventory.services import execute, number, _fingerprint
    data = decode_new(actor, token)
    source = data['source']
    number(price, Decimal('.01'), zero=True)
    if not reason.strip() or len(reason) > 350: raise ValidationError('Informe o motivo de até 350 caracteres.')
    qty = Decimal(source['quantity']) if include_stock else Decimal(0)
    if include_stock:
        number(qty, Decimal('.0001'), zero=True)
        if qty > 0: number(cost, Decimal('.000001'))
    fingerprint = _fingerprint([token, name, price, include_stock, cost, reason])
    # Only a read before the transaction. Catalog creation and stock entry commit together.
    latest = bling.read('/produtos/' + source['id']).get('data')
    if not isinstance(latest, dict) or str(latest.get('id')) != source['id']:
        raise ValidationError('Produto externo indisponível.')
    expected = external(latest, source['quantity'])
    if any(expected[k] != source[k] for k in ('id', 'sku', 'unit')) or Decimal(expected['price']) != Decimal(source['price']) or str(latest.get('nome', '')).strip() != source['name']:
        raise ValidationError('Cadastro mudou no Bling. Prepare a importação novamente.')
    if include_stock:
        if data['deposit'] not in dict(deposits()): raise ValidationError('Depósito Bling indisponível.')
        balances = remote_balances(data['deposit'], [source['id']])
        if source['id'] not in balances or Decimal(balances[source['id']]) != qty: raise ValidationError('Saldo mudou no Bling. Consulte novamente.')
    with transaction.atomic():
        domain_lock()
        previous = AuditLog.objects.filter(operation='bling_create_product', after__key=data['key']).first()
        if previous:
            if previous.after['fingerprint'] != fingerprint: raise ValidationError('Prévia já utilizada com outros dados.')
            return Product.objects.get(pk=previous.after['product'])
        if Product.objects.filter(sku=source['sku']).exists() or AuditLog.objects.filter(operation='bling_create_product', after__remote_id=source['id']).exists():
            raise ValidationError('Produto já cadastrado no MVet. Use a comparação para corrigir diferenças.')
        location = StockLocation.objects.get(pk=data['location'], active=True)
        product = save_product(actor=actor, data={'sku': source['sku'], 'name': name, 'unit': source['unit'], 'kind': 'SIMPLE'})
        configure_fixed_price(actor=actor, product_id=product.pk, price=price)
        if qty > 0:
            execute(actor=actor, key=data['key'], kind='ADJUST_IN', date=timezone.localdate(),
                    reason='Cadastro a partir do Bling: ' + reason, product_id=product.pk, location_id=location.pk, quantity=qty, cost=cost)
        audit(actor, product, 'bling_create_product', after={'key': data['key'], 'fingerprint': fingerprint,
            'product': product.pk, 'remote_id': source['id'], 'source': source, 'price': str(price),
            'quantity': str(qty), 'cost': str(cost) if qty > 0 else None, 'location': location.pk, 'deposit': data['deposit'], 'reason': reason})
        return product


def bulk_preview(*, actor, tokens, field, direction, reason):
    """Validate the complete selection before allowing any batch write."""
    master(actor)
    if not tokens or len(tokens) > 50:
        raise ValidationError('Selecione de 1 a 50 produtos da página.')
    if field not in ('price', 'quantity') or direction not in ('mvet', 'bling'):
        raise ValidationError('Selecione o campo e o sistema que será corrigido.')
    if not reason.strip() or len(reason) > 350:
        raise ValidationError('Informe um motivo de até 350 caracteres.')
    rows, seen = [], set()
    for token in tokens:
        snapshot = decode(actor, token)
        if snapshot['product'] in seen:
            raise ValidationError('Produto repetido na seleção.')
        seen.add(snapshot['product'])
        source = 'remote' if direction == 'mvet' else 'local'
        destination = 'local' if direction == 'mvet' else 'remote'
        before, after = snapshot[destination][field], snapshot[source][field]
        if Decimal(before) == Decimal(after):
            continue
        rows.append({'token': token, 'sku': snapshot['local']['sku'], 'before': before, 'after': after})
    if not rows:
        raise ValidationError('Os produtos selecionados não têm diferenças no campo escolhido.')
    return rows


def apply_bulk(*, actor, tokens, field, direction, reason):
    rows = bulk_preview(actor=actor, tokens=tokens, field=field, direction=direction, reason=reason)
    results = []
    for row in rows:
        try:
            correction = apply(actor=actor, token=row['token'], field=field, direction=direction, reason=reason)
            results.append({'sku': row['sku'], 'correction': correction, 'status': correction.status, 'message': correction.message})
        except (ValidationError, Product.DoesNotExist, StockLocation.DoesNotExist) as exc:
            message = '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Produto ou depósito indisponível.'
            results.append({'sku': row['sku'], 'correction': None, 'status': 'FAILED', 'message': message})
    return results
