"""Cash matrix in printable day groups, matching the chosen screen mode."""
from reportlab.lib import colors
from reportlab.platypus import TableStyle
from .pdf_layout import Report, p, fmt, table, NUMBER, HEADER, HEADING, SECTION, SMALL, BOLD_NUMBER


def render(dataset, company):
    report = Report('Saldos e fluxo de caixa', company)
    days = sorted({row['date'] for row in dataset.cash})
    accounts = {row['account'].pk: str(row['account']) for row in dataset.cash}
    lookup = {(row['account'].pk, row['date']): row for row in dataset.cash}
    projected = dataset.cash_mode == 'projected'
    keys = ['projected_credits', 'projected_debits', 'projected'] if projected else ['credits', 'debits', 'final']
    story = []
    for offset in range(0, len(days), 3):
        group = days[offset:offset+3]
        if not offset:
            story += [p('Saldos e fluxo de caixa', HEADING), p(dataset.notes, SMALL)]
        story.append(p(('Realizado + previsto' if projected else 'Somente realizado') + ' · ' + fmt(group[0]) + ' a ' + fmt(group[-1]), SECTION))
        data = [[p('Banco / conta', HEADER)]]
        for day in group:
            data[0] += [p(fmt(day), HEADER), p(''), p('')]
        data.append([p('')]+[p(label, SMALL) for _ in group for label in ('Entradas', 'Saídas', 'Saldo')])
        for pk, name in accounts.items():
            row = [p(name)]
            for day in group:
                record = lookup.get((pk, day))
                for key in keys:
                    value = record[key] if record else None
                    row.append(p(value, BOLD_NUMBER if key == keys[-1] else NUMBER))
            data.append(row)
        total = [p('Total das contas')]
        for day in group:
            for key in keys:
                total.append(p(sum(record[key] for record in dataset.cash if record['date'] == day), BOLD_NUMBER))
        data.append(total)
        number_width = (report.width-150)/(len(group)*3)
        grid = table(data, [150]+[number_width]*(len(group)*3), repeat=2)
        commands = [('SPAN', (0,0), (0,1)), ('BACKGROUND', (0,1), (0,1), colors.HexColor('#1b1c4a')),
                    ('LINEABOVE', (0,-1), (-1,-1), 1, colors.HexColor('#1b1c4a'))]
        for index in range(len(group)):
            start = 1+index*3
            commands += [('SPAN', (start,0), (start+2,0)),
                         ('LINEAFTER', (start+2,0), (start+2,-1), .7, colors.HexColor('#9cb0bc'))]
        grid.setStyle(TableStyle(commands))
        story.append(grid)
    return report.build(story)
