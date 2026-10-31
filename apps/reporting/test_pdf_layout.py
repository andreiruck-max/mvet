"""Rendered pagination regressions; synthetic data only, no database required."""
import re
from datetime import date, timedelta
from decimal import Decimal as D
from types import SimpleNamespace as N
from unittest.mock import patch
from django.test import SimpleTestCase
from reportlab.platypus import Paragraph, Spacer
from .datasets import Dataset
from .files import pdf
from .pdf_layout import Report, p, table, HEADING, SECTION, HEADER


def pages(content):
    return len(re.findall(rb'/Type\s*/Page\b', content))


def render_with_text(renderer, *args):
    """Observe text actually drawn, including split tables and repeated headers."""
    drawn = []
    original = Paragraph.draw
    def draw(paragraph):
        text = paragraph.getPlainText()
        if not text:
            # Split paragraphs may have pre-laid-out lines instead of source text.
            lines = getattr(getattr(paragraph, 'blPara', None), 'lines', [])
            text = ' '.join(' '.join(line[1]) if isinstance(line, tuple) else
                            ''.join(getattr(word, 'text', '') for word in line.words) for line in lines)
        drawn.append((paragraph.canv.getPageNumber(), text))
        return original(paragraph)
    with patch.object(Paragraph, 'draw', draw):
        content = renderer(*args)
    return content, drawn


class PDFLayoutTests(SimpleTestCase):
    def test_long_table_starts_below_heading_on_first_page(self):
        report = Report('Teste', 'Empresa sintética')
        data = [[p('Referência', HEADER), p('Descrição', HEADER)]]
        data += [[p(f'ITEM-{i:03}'), p('Descrição de conferência')] for i in range(65)]
        content, drawn = render_with_text(report.build, [p('Resumo', HEADING), p('Introdução'),
            p('Itens', SECTION), table(data, [120, report.width-120])])
        self.assertGreater(pages(content), 1)
        self.assertIn((1, 'Itens'), drawn)
        self.assertIn((1, 'ITEM-000'), drawn)
        for i in range(65):
            self.assertEqual(sum(text == f'ITEM-{i:03}' for _, text in drawn), 1)
        for page in range(1, pages(content)+1):
            self.assertIn((page, 'Referência'), drawn)

    def test_small_stock_sections_and_wide_blocks_share_page(self):
        stock = Dataset('Estoque', ['SKU','Produto','Quantidade','Valor'],
                        [['001','Produto sintético',D('2'),D('10')]])
        stock.locations = Dataset('Locais', ['SKU','Produto','Local','Quantidade','Valor'],
                                  [['001','Produto sintético','Depósito',D('2'),D('10')]])
        self.assertEqual(pages(pdf(stock, 'Empresa sintética')), 1)
        wide = Dataset('Compras', [f'Coluna {i}' for i in range(14)], [list(range(14))])
        content, drawn = render_with_text(pdf, wide, 'Empresa sintética')
        self.assertEqual(pages(content), 1)
        self.assertTrue(any(text == 'Coluna 13' for _, text in drawn))

    def test_short_sales_channels_share_page(self):
        headers = ['DATA','NF','SÉRIE','SITUAÇÃO','VALOR','TOTAL','SIMPLES','ESTOQUE','PRODUTOS']
        groups = [Dataset('Vendas', headers, [[date(2026,10,1),str(i),'1','Confirmada',D('10'),D('10'),D('1'),'Loja','1 × Produto']],
                          f'Canal {i}', {'count':1,'revenue':D('10')}) for i in (1,2)]
        ds = Dataset('Vendas', headers, [], totals={'count':2,'revenue':D('20')})
        ds.groups = groups
        content, drawn = render_with_text(pdf, ds, 'Empresa sintética')
        self.assertEqual(pages(content), 1)
        self.assertTrue(any('NF 1 / 1' in text for _,text in drawn))
        self.assertTrue(any('NF 2 / 1' in text for _,text in drawn))

    def test_cash_keeps_three_day_groups_without_forcing_pages(self):
        account = N(pk=1)
        rows = [dict(account=account,date=date(2026,10,1)+timedelta(days=i),
                     credits=D('10'),debits=D('2'),final=D('8')) for i in range(6)]
        ds = Dataset('Caixa', [], [], cash=rows)
        content, drawn = render_with_text(pdf, ds, 'Empresa sintética')
        self.assertEqual(pages(content), 1)
        for i in range(1,7):
            self.assertTrue(any(f'{i:02}/10/2026' == text for _,text in drawn))

    def test_oversized_row_continues_without_layout_error(self):
        ds = Dataset('Texto extenso', ['Referência','Descrição'],
                     [['INÍCIO', 'Descrição extensa para conferência. '*1200 + ' FIM-DO-REGISTRO']])
        content, drawn = render_with_text(pdf, ds, 'Empresa sintética')
        self.assertGreater(pages(content), 1)
        self.assertTrue(any('FIM-DO-REGISTRO' in text for _,text in drawn))

    def test_heading_moves_with_first_row_when_page_is_full(self):
        report = Report('Teste', 'Empresa sintética')
        grid = table([[p('Coluna', HEADER)], [p('PRIMEIRA-LINHA')]], [report.width])
        content, drawn = render_with_text(report.build,
            [p('Introdução'), Spacer(1, 460), p('Seção seguinte', SECTION), grid])
        self.assertEqual(pages(content), 2)
        self.assertIn((2, 'Seção seguinte'), drawn)
        self.assertIn((2, 'PRIMEIRA-LINHA'), drawn)
