"""Shared print design; receives only already-authorized report projections."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import CondPageBreak, LongTable, Paragraph, SimpleDocTemplate, TableStyle

# ReportLab ships these licensed fonts: embed them for consistent accents and spacing
# on Windows, Linux and browser PDF viewers without system-font dependencies.
_font_dir = Path(reportlab.__file__).parent / 'fonts'
pdfmetrics.registerFont(TTFont('MVet', str(_font_dir / 'Vera.ttf')))
pdfmetrics.registerFont(TTFont('MVet-Bold', str(_font_dir / 'VeraBd.ttf')))

INK = colors.HexColor('#20313d')
BRAND = colors.HexColor('#1b1c4a')
BORDER = colors.HexColor('#ccd8df')
SOFT = colors.HexColor('#eef3f6')
BODY = ParagraphStyle('body', fontName='MVet', fontSize=8.5, leading=11, textColor=INK)
NUMBER = ParagraphStyle('number', parent=BODY, alignment=2)
SMALL = ParagraphStyle('small', parent=BODY, fontSize=7.5, leading=9.5, textColor=colors.HexColor('#586b78'))
HEADER = ParagraphStyle('header', parent=BODY, fontName='MVet-Bold', fontSize=8, leading=10.5, textColor=colors.white)
HEADER_NUMBER = ParagraphStyle('header_number', parent=HEADER, alignment=2)
BOLD = ParagraphStyle('bold', parent=BODY, fontName='MVet-Bold')
BOLD_NUMBER = ParagraphStyle('bold_number', parent=BOLD, alignment=2)
HEADING = ParagraphStyle('heading', parent=BODY, fontName='MVet-Bold', fontSize=16, leading=20, spaceAfter=6, keepWithNext=True)
SECTION = ParagraphStyle('section', parent=HEADING, fontSize=10.5, leading=14, spaceBefore=10, spaceAfter=4)


def fmt(value):
    if value is None:
        return '—'
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, Decimal):
        return f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return str(value)


def p(value, style=BODY):
    content = escape(fmt(value)).replace('\n', '<br/>')
    if isinstance(value, (Decimal, int)) and value < 0:
        content = '<font color="#bc202b">' + content + '</font>'
    return Paragraph(content, style)


def table(data, widths, *, repeat=1):
    obj = LongTable(data, colWidths=widths, repeatRows=repeat, splitInRow=1, hAlign='LEFT')
    obj.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, repeat), (-1, -1), [colors.white, SOFT]),
        ('LINEBELOW', (0, 0), (-1, 0), .8, BRAND),
        ('LINEBELOW', (0, repeat), (-1, -1), .35, BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    if repeat > 1:
        obj.setStyle(TableStyle([('BACKGROUND', (0, 1), (-1, repeat-1), SOFT),
                                ('LINEBELOW', (0, repeat-1), (-1, repeat-1), 1, BRAND)]))
    return obj


class Report:
    def __init__(self, title, company, *, wide=True):
        self.out = BytesIO()
        self.page = landscape(A4) if wide else A4
        self.width = self.page[0] - 76  # Account for the frame's 6pt padding on each side.
        self.title, self.company = title, company
        self.document = SimpleDocTemplate(self.out, pagesize=self.page, leftMargin=32, rightMargin=32,
                                          topMargin=44, bottomMargin=36, title=title, author=company)

    def decorate(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BRAND)
        canvas.setFont('MVet-Bold', 9)
        # A long company name must not collide with the page identification.
        name = self.company
        while canvas.stringWidth(name, 'MVet-Bold', 9) > self.width * .60 and len(name) > 1:
            name = name[:-2] + '…'
        canvas.drawString(32, self.page[1]-28, name)
        canvas.setFont('MVet', 8)
        canvas.drawRightString(self.page[0]-32, self.page[1]-28, 'MVet · Relatório gerencial')
        canvas.setStrokeColor(BORDER)
        canvas.line(32, self.page[1]-36, self.page[0]-32, self.page[1]-36)
        canvas.line(32, 30, self.page[0]-32, 30)
        canvas.setFillColor(INK)
        canvas.drawString(32, 18, 'MVet · Valores monetários em R$')
        canvas.drawRightString(self.page[0]-32, 18, f'Página {doc.page}')
        canvas.restoreState()

    def flowing_headings(self, story):
        """Keep a caption with the first table row, not with the entire LongTable.

        ReportLab's automatic keepWithNext otherwise moves a long table to a
        fresh page even when several rows fit beneath its caption here.
        """
        result = []
        index = 0
        frame_height = self.document.height - 12
        while index < len(story):
            end = index
            while end < len(story) and story[end].getKeepWithNext():
                end += 1
            if end > index and end < len(story) and isinstance(story[end], LongTable):
                captions = story[index:end]
                grid = story[end]
                grid.wrap(self.width, frame_height)
                # Heights are measured by ReportLab, including wrapping and padding.
                first_rows = sum(grid._rowHeights[:grid.repeatRows + 1])
                caption_height = sum(item.wrap(self.width, frame_height)[1] +
                                     item.getSpaceBefore() + item.getSpaceAfter() for item in captions)
                result.append(CondPageBreak(min(frame_height, caption_height + first_rows + 2)))
                for item in captions:
                    item.keepWithNext = False
                result.extend(captions)
                result.append(grid)
                index = end + 1
            else:
                result.append(story[index])
                index += 1
        return result

    def build(self, story):
        self.document.build(self.flowing_headings(story), onFirstPage=self.decorate, onLaterPages=self.decorate)
        return self.out.getvalue()


def weights(headers, rows):
    """Give descriptions space without stretching dates and currency columns."""
    result = []
    for index, label in enumerate(headers):
        upper = label.upper()
        if any(word in upper for word in ('PRODUTO', 'DESCRI', 'CATEGORIA', 'LINHA GERENCIAL', 'INDICADOR')):
            weight = 3.5
        elif any(word in upper for word in ('FORNECEDOR', 'CONTA', 'LOCAL', 'CANAL')):
            weight = 2
        elif upper in ('NF', 'SKU', 'SÉRIE', 'QTD'):
            weight = .85
        else:
            weight = 1.25
        result.append(weight)
    return result


def dataset_table(dataset, width, indexes):
    headers = [dataset.headers[i] for i in indexes]
    proportions = weights(headers, dataset.rows)
    widths = [width * weight / sum(proportions) for weight in proportions]
    data = [[p(label, HEADER_NUMBER if any(isinstance(row[indexes[i]], (Decimal, int)) for row in dataset.rows) else HEADER) for i, label in enumerate(headers)]]
    total_labels = {'Receita operacional', 'Margem de contribuição', 'EBITDA gerencial', 'Resultado gerencial'}
    subtotal_rows = []
    for row in dataset.rows:
        cells = []
        subtotal = str(row[0]) in total_labels
        if subtotal: subtotal_rows.append(len(data))
        for index in indexes:
            value = row[index]
            if dataset.headers[index] == 'Margem %' and value is not None:
                value *= 100
            style = (BOLD_NUMBER if subtotal else NUMBER) if isinstance(value, (Decimal, int)) else (BOLD if subtotal else BODY)
            cells.append(p(value, style))
        data.append(cells)
    if not dataset.rows:
        data.append([p('Sem registros no período.')]+[p('') for _ in indexes[1:]])
    result = table(data, widths)
    for row in subtotal_rows:
        result.setStyle(TableStyle([('BACKGROUND', (0, row), (-1, row), SOFT), ('LINEABOVE', (0, row), (-1, row), .8, BORDER)]))
    return result
