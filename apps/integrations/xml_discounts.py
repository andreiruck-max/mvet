"""Bounded read-only XML enrichment; never persist signed URLs or raw XML."""
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from urllib.error import URLError
import xml.etree.ElementTree as ET
from django.core.exceptions import ValidationError
from .normalization import decimal_text

LIMIT = 2_000_000
NS = {'n': 'http://www.portalfiscal.inf.br/nfe'}


def extract(raw, payload):
    if len(raw) > LIMIT or b'\x00' in raw or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValidationError('XML da nota excede o limite ou contém declaração não permitida.')
    try:
        root = ET.fromstring(raw)
        infos = list(root.iter('{'+NS['n']+'}infNFe'))
        if len(infos) != 1:
            raise ValueError
        info = infos[0]
        if info.get('Id') != 'NFe' + str(payload.get('chaveAcesso', '')):
            raise ValueError
        total = info.find('n:total/n:ICMSTot', NS)
        if total is None:
            raise ValueError
        def money(node, name):
            return Decimal(decimal_text(node.findtext('n:'+name, namespaces=NS), 2))
        if money(total, 'vNF') != Decimal(decimal_text(payload.get('valorNota'), 2)):
            raise ValueError
        products = info.findall('n:det/n:prod', NS)
        items = payload.get('itens', [])
        if not products or len(products) != len(items):
            raise ValueError
        discounts = []
        for product, item in zip(products, items):
            if product.findtext('n:cProd', namespaces=NS) != str(item.get('codigo')):
                raise ValueError
            quantity = Decimal(decimal_text(product.findtext('n:qCom', namespaces=NS), 4))
            price = Decimal(decimal_text(product.findtext('n:vUnCom', namespaces=NS), 10))
            if quantity != Decimal(decimal_text(item.get('quantidade'), 4)) or price != Decimal(decimal_text(item.get('valor'))):
                raise ValueError
            gross = money(product, 'vProd')
            if gross != (quantity * price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP):
                raise ValueError
            discount = Decimal(decimal_text(product.findtext('n:vDesc', default='0', namespaces=NS), 2))
            if discount > gross:
                raise ValueError
            discounts.append(discount)
        discount = money(total, 'vDesc')
        if sum(discounts) != discount:
            raise ValueError
        return {'total': str(discount), 'items': [str(value) for value in discounts]}
    except (ET.ParseError, ValueError, TypeError, AttributeError, KeyError):
        raise ValidationError('XML não corresponde aos valores ou itens da nota. Reconsulte antes de confirmar.') from None


def enrich(payload):
    from .bling import BlingError, NoRedirect
    if not isinstance(payload, dict):
        raise BlingError('Detalhe inválido.')
    result = dict(payload)
    result.pop('_xml_discounts', None)
    link = payload.get('xml')
    if not link:
        return result
    try:
        url = urlsplit(link)
        if url.scheme != 'https' or url.hostname not in ('www.bling.com.br', 'bling.com.br') or url.port not in (None, 443) or url.username or url.password or url.fragment:
            raise ValueError
        # No OAuth credentials, cookies or redirects on document downloads.
        with build_opener(NoRedirect()).open(Request(link, headers={'Accept': 'application/xml'}), timeout=8) as response:
            raw = response.read(LIMIT + 1)
        result['_xml_discounts'] = extract(raw, payload)
        return result
    except (URLError, OSError, ValueError, TypeError, ValidationError):
        # Optional prefill: unavailable/untrusted XML must not block staging.
        # No discount is inferred; the operator reviews it in the local form.
        return result
