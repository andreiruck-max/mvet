"""Bounded XLSX positions: saved values only, no additions or duplicate consolidation."""
import io
import json
import posixpath
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.products.models import Product
from .models import StockLocation
from .services import quant, number, QTY, MONEY

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
MAX_ROWS = 5000


def normalized(value):
    text = str(value).strip().lower().replace('_', ' ')
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).split())


ALIASES = {
    'sku': 'sku', 'codigo': 'sku', 'produto': 'name', 'nome': 'name', 'descricao': 'name',
    'quantidade': 'quantity', 'qtd': 'quantity', 'qtd total positiva': 'quantity', 'saldo': 'quantity',
    'custo medio': 'cost', 'custo': 'cost', 'custo medio unitario': 'cost', 'custo unitario': 'cost',
    'unidade': 'unit', 'un': 'unit', 'deposito': 'location', 'local': 'location',
    'valor total': 'value', 'valor do estoque': 'value',
}


def xml(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValidationError('XML com entidades não é permitido.')
    return ET.fromstring(raw)


def read_xlsx(raw):
    if len(raw) > 5_000_000:
        raise ValidationError('Arquivo excede 5 MB.')
    try:
        with ZipFile(io.BytesIO(raw)) as book:
            if len(book.infolist()) > 300 or sum(i.file_size for i in book.infolist()) > 25_000_000:
                raise ValidationError('Planilha excede o limite descompactado de 25 MB.')
            workbook = xml(book.read('xl/workbook.xml'))
            first = workbook.find('s:sheets/s:sheet', NS)
            rid = first.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            rels = xml(book.read('xl/_rels/workbook.xml.rels'))
            rel = next(r for r in rels if r.get('Id') == rid)
            target = rel.attrib['Target']
            path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
            if rel.get('TargetMode') == 'External' or not path.startswith('xl/worksheets/'):
                raise ValidationError('Primeira aba deve ser uma planilha de dados local.')
            shared = []
            if 'xl/sharedStrings.xml' in book.namelist():
                shared = [''.join(n.itertext()) for n in xml(book.read('xl/sharedStrings.xml')).findall('s:si', NS)]
            rows = []
            root = xml(book.read(path))
            for row in root.findall('s:sheetData/s:row', NS):
                cells = {}
                for cell in row.findall('s:c', NS):
                    if cell.find('s:f', NS) is not None and (cell.get('t', 'n') != 'n' or not cell.findtext('s:v', '', NS)):
                        raise ValidationError(f"Linha {row.get('r')}: fórmula sem resultado numérico salvo. Recalcule e salve no Excel, ou copie e cole como valores.")
                    if cell.get('t') in ('e', 'b', 'd'):
                        raise ValidationError(f"Linha {row.get('r')}: célula com erro, data ou valor lógico não permitido.")
                    letters = ''.join(c for c in cell.attrib['r'] if c.isalpha())
                    index = 0
                    for letter in letters:
                        index = index * 26 + ord(letter.upper()) - 64
                    if not 1 <= index <= 30:
                        raise ValidationError('Use no máximo 30 colunas.')
                    value = cell.findtext('s:v', '', NS)
                    if cell.get('t') == 's':
                        value = shared[int(value)]
                    elif cell.get('t') == 'inlineStr':
                        value = ''.join(cell.find('s:is', NS).itertext())
                    if len(value) > 2000:
                        raise ValidationError('Célula excede 2.000 caracteres.')
                    cells[index - 1] = value.strip()
                rows.append((int(row.get('r')), [cells.get(i, '') for i in range(max(cells, default=-1) + 1)]))
                if len(rows) > MAX_ROWS + 1:
                    raise ValidationError('Use no máximo 5.000 linhas de produtos.')
            if not rows or not any(rows[0][1]):
                raise ValidationError('Primeira linha deve conter os cabeçalhos.')
            return rows
    except (BadZipFile, KeyError, ET.ParseError, ValueError, AttributeError, IndexError, StopIteration, RuntimeError) as exc:
        raise ValidationError('XLSX inválido. Salve como Pasta de Trabalho do Excel (.xlsx).') from exc


def decimal_value(raw, quantum):
    text = str(raw).replace('R$', '').replace(' ', '').replace('\u00a0', '')
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    result = Decimal(text)
    if not result.is_finite() or result < 0 or result >= Decimal('1000000000000'):
        raise ValidationError('Informe um número não negativo, abaixo de um trilhão.')
    rounded = result.quantize(quantum, rounding=ROUND_HALF_UP)
    if quantum == QTY and abs(result - rounded) > Decimal('0.000000001'):
        raise ValidationError('Quantidade deve ter no máximo 4 casas decimais.')
    return number(rounded, quantum, zero=True)


def snapshot_from_xlsx(raw, *, location=None, mode='current', base_date=None, complete=False):
    rows = read_xlsx(raw)
    headers = [ALIASES.get(normalized(h)) for h in rows[0][1]]
    known = [h for h in headers if h]
    if len(known) != len(set(known)):
        raise ValidationError('Cabeçalhos repetidos. Use uma coluna por informação.')
    if not {'sku', 'quantity', 'cost'} <= set(known):
        raise ValidationError('Colunas obrigatórias: SKU, Quantidade e Custo médio. Produto é obrigatório para novos cadastros.')
    if not location and 'location' not in known:
        raise ValidationError('Escolha o depósito na tela ou inclua a coluna Depósito.')
    locations = {normalized(loc.name): loc for loc in StockLocation.objects.filter(active=True)}
    products = {p.sku: p for p in Product.objects.all()}
    groups = {}; seen = set(); definitions = {}; errors = []
    for line, values in rows[1:]:
        if not any(values):
            continue
        data = {key: values[i] if i < len(values) else '' for i, key in enumerate(headers) if key}
        try:
            sku = data['sku'].strip()
            if not sku:
                raise ValidationError('SKU ausente.')
            chosen = location
            if data.get('location'):
                chosen = locations.get(normalized(data['location']))
                if not chosen:
                    raise ValidationError('Depósito não encontrado ou inativo.')
                if location and chosen.pk != location.pk:
                    raise ValidationError('Depósito da linha difere do selecionado na tela.')
            if not chosen:
                raise ValidationError('Depósito ausente.')
            key = (chosen.pk, sku)
            if key in seen:
                raise ValidationError(f'SKU {sku} repetido neste depósito. Corrija a planilha; quantidades não serão somadas.')
            seen.add(key)
            p = products.get(sku)
            name = p.name if p else data.get('name', '')
            unit = p.unit if p else data.get('unit') or 'UN'
            if not name:
                raise ValidationError(f'SKU {sku}: informe Produto para cadastrar o novo item.')
            if not p:
                if sku in definitions and definitions[sku] != (name, unit):
                    raise ValidationError(f'SKU {sku}: nome ou unidade do novo produto diverge entre depósitos.')
                definitions[sku] = (name, unit)
            qty = decimal_value(data['quantity'], QTY)
            cost = decimal_value(data['cost'], MONEY)
            value = quant(qty * cost)
            if data.get('value'):
                value = decimal_value(data['value'], MONEY)
                if (not qty and value) or abs(value - quant(qty * cost)) > max(MONEY, qty * MONEY):
                    raise ValidationError(f'SKU {sku}: Valor total difere de quantidade × custo médio.')
            group = groups.setdefault(chosen.name, dict(location=chosen.name, complete=complete, items=[]))
            group['items'].append(dict(sku=sku,name=name,unit=unit,quantity=str(qty),cost=str(cost),value=str(value)))
        except (ValidationError, InvalidOperation, ValueError) as exc:
            detail = '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Número inválido.'
            errors.append(f'Linha {line}: {detail}')
            if len(errors) >= 30:
                break
    if errors:
        raise ValidationError(errors)
    if not groups:
        raise ValidationError('Planilha sem produtos. Nenhum saldo será zerado.')
    day = timezone.localdate() if mode == 'current' else base_date
    if not day:
        raise ValidationError('Informe a data-base.')
    return json.dumps(dict(version=3, mode=mode, date=str(day), locations=list(groups.values())))


def template_xlsx():
    """Empty, values-only Excel template. No real commercial data."""
    out = io.BytesIO()
    headers = ['SKU', 'Produto', 'Quantidade', 'Custo médio', 'Unidade', 'Depósito', 'Valor total']
    cells = ''.join(f'<c r="{chr(65+i)}1" t="inlineStr"><is><t>{escape(h)}</t></is></c>' for i,h in enumerate(headers))
    with ZipFile(out, 'w') as book:
        book.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        book.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        book.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Estoque" sheetId="1" r:id="rId1"/></sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        book.writestr('xl/styles.xml', '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        book.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="18" customWidth="1" style="1"/><col min="2" max="2" width="45" customWidth="1"/><col min="3" max="5" width="20" customWidth="1"/><col min="6" max="6" width="28" customWidth="1"/><col min="7" max="7" width="20" customWidth="1"/></cols><sheetData><row r="1">{cells}</row></sheetData><autoFilter ref="A1:G1"/></worksheet>')
    return out.getvalue()
