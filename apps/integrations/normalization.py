"""Strict, allowlisted projection of the official NF-e detail contract."""
from datetime import date
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError


def decimal_text(value, places=6):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number >= Decimal('1000000000000'):
            raise ValueError
        if number != number.quantize(Decimal(1).scaleb(-places)):
            raise ValueError
        return format(number.quantize(Decimal(1).scaleb(-places)), 'f')
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Valor externo inválido ou com precisão excessiva.')


def text(value, maximum):
    value = str(value if value is not None else '').strip()
    if len(value) > maximum:
        raise ValidationError('Campo externo excede o limite aceito.')
    return value


def normalize(payload, issuer):
    if not isinstance(payload, dict):
        raise ValidationError('Resposta de nota inválida.')
    key = text(payload.get('chaveAcesso'), 44)
    if len(key) != 44 or not key.isascii() or not key.isdecimal() or key[6:20] != issuer:
        raise ValidationError('Chave ausente, inválida ou de outro emitente. Confira a conexão.')
    number = text(payload.get('numero'), 30)
    series = text(payload.get('serie'), 10)
    if not number.isdecimal() or not series.isdecimal():
        raise ValidationError('Número ou série inválidos.')
    if str(int(key[25:34])) != str(int(number)) or str(int(key[22:25])) != str(int(series)):
        raise ValidationError('Número ou série não correspondem à chave fiscal.')
    try:
        issued = date.fromisoformat(str(payload['dataEmissao'])[:10])
    except (KeyError, ValueError):
        raise ValidationError('Data de emissão inválida.')
    items = payload.get('itens')
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ValidationError('Nota precisa conter de 1 a 100 itens.')
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError('Item inválido.')
        rows.append({
            'code': text(item.get('codigo'), 120), 'name': text(item.get('descricao'), 240),
            'unit': text(item.get('unidade'), 12).upper(),
            'quantity': decimal_text(item.get('quantidade'), 4),
            'price': decimal_text(item.get('valor')),
            'type': text(item.get('tipo'), 1), 'cfop': text(item.get('cfop'), 4),
        })
    store = payload.get('loja') or {}
    if not isinstance(store, dict): raise ValidationError('Loja externa inválida.')
    return {'number': str(int(number)), 'series': str(int(series)), 'key': key,
            'date': issued.isoformat(), 'status': text(payload.get('situacao'), 20),
            'type': text(payload.get('tipo'), 1), 'purpose': text(payload.get('finalidade'), 1),
            'store': text(store.get('id'), 40),
            'order': text(payload.get('numeroPedidoLoja'), 120),
            'total': decimal_text(payload.get('valorNota'), 2),
            'freight': decimal_text(payload.get('valorFrete', 0), 2), 'items': rows}


def eligibility(source, *, purpose_reviewed=False):
    if source['status'] != '5' or source['type'] != '1':
        raise ValidationError('Somente NF autorizada e de saída pode gerar venda.')
    purpose = source.get('purpose', '')
    if purpose not in ('', '1'):
        raise ValidationError('Finalidade externa diferente de normal. Nota bloqueada.')
    if not purpose and purpose_reviewed is not True:
        raise ValidationError('O Bling não informou a finalidade. Confira o documento e confirme explicitamente que é uma venda de finalidade normal.')
    for row in source['items']:
        # Fail closed. Nature/CFOP still requires the operator's explicit review.
        cfop = row['cfop']
        if row['type'] != 'P' or len(cfop) != 4 or cfop[0] not in '567' or cfop[1] != '1':
            raise ValidationError('Item não identificado como venda de mercadoria. Confira CFOP/natureza; remessas e transferências não são vendas.')
        if not row['code'] or not row['unit'] or Decimal(row['quantity']) <= 0:
            raise ValidationError('Item sem código, unidade ou quantidade válida.')
