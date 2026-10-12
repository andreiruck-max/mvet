"""Print sales by channel, preserving complete items and authorized metrics."""
from reportlab.platypus import Spacer, PageBreak
from .pdf_layout import Report, p, fmt, table, BODY, NUMBER, SMALL, HEADER, HEADER_NUMBER, HEADING, SECTION


def render(dataset, company):
    report = Report('Relatório de vendas', company)
    width = report.width
    margins = 'contribution' in dataset.totals
    costs = 'cmv' in dataset.totals
    keys = ['count', 'revenue'] + (['cmv'] if costs else []) + (['tax_amount', 'contribution', 'margin'] if margins else [])
    labels = {'count':'Vendas', 'revenue':'Receita', 'cmv':'CMV', 'tax_amount':'Imposto', 'contribution':'Contribuição', 'margin':'Margem %'}
    story = [p('Relatório de vendas', HEADING), p(dataset.notes, SMALL), p('Resumo por canal', SECTION)]
    summary = [[p('Canal', HEADER)] + [p(labels[key], HEADER_NUMBER) for key in keys]]
    for name, totals in [('Total da empresa', dataset.totals)] + [(g.notes, g.totals) for g in dataset.groups]:
        summary.append([p(name)] + [p(totals.get(key), NUMBER) for key in keys])
    story += [table(summary, [width*.32] + [width*.68/len(keys)]*len(keys), repeat=2), Spacer(1, 8),
              p('Totais somente de vendas confirmadas. Rascunhos e cancelamentos ficam identificados e não compõem os totais.', SMALL)]
    for group in dataset.groups:
        story += [PageBreak(), p(group.notes, HEADING),
                  p(f"{group.totals['count']} vendas confirmadas · Receita R$ {fmt(group.totals['revenue'])}", BODY)]
        totals = []
        for key, label in [('discount','Desconto'), ('shipping_received','Frete recebido'), ('shipping_paid','Frete pago'), ('fees','Taxas'), ('extra_costs_total','Extras / MDR'), ('difal','DIFAL'), ('commission','Comissão'), ('other_costs','Outros custos'), ('revenue_adjustment','Ajuste de receita')]:
            if group.totals.get(key):
                totals.append(label + ': R$ ' + fmt(group.totals[key]))
        if totals:
            story.append(p('Totais do canal · ' + ' · '.join(totals), SMALL))
        story.append(Spacer(1, 12))
        financial = ['TOTAL'] + (['CMV histórico'] if costs else []) + ['SIMPLES'] + (['Margem de contribuição','Margem %'] if margins else [])
        labels2 = {'TOTAL':'Receita', 'SIMPLES':'Imposto', 'Margem de contribuição':'Contribuição', 'CMV histórico':'CMV'}
        total_keys = {'TOTAL':'revenue', 'CMV histórico':'cmv', 'SIMPLES':'tax_amount', 'Margem de contribuição':'contribution', 'Margem %':'margin'}
        data = [[p('Data / NF', HEADER), p('Produtos e quantidades', HEADER)] + [p(labels2.get(key,key), HEADER_NUMBER) for key in financial]]
        data.append([p('TOTAL DO CANAL', SMALL), p('Somente confirmadas', SMALL)] + [p(group.totals.get(total_keys[key]), NUMBER) for key in financial])
        for values in group.rows:
            row = dict(zip(group.headers, values))
            identity = fmt(row['DATA']) + '\nNF ' + str(row['NF']) + ' / ' + str(row['SÉRIE'])
            if row['SITUAÇÃO'] != 'Confirmada':
                identity += '\n' + row['SITUAÇÃO']
            details = ['Produtos: R$ ' + fmt(row['VALOR'])]
            for key in ['DESCONTO','FRETE RECEBIDO','FRETE PAGO','TAXAS','EXTRAS / MDR','DIFAL','COMISSÃO','OUTROS CUSTOS','AJUSTE GERENCIAL DA RECEITA']:
                if row.get(key):
                    details.append(key.title() + ': R$ ' + fmt(row[key]))
            details.append('Estoque: ' + str(row['ESTOQUE']))
            # Bounded item groups repeat invoice identification on continuation rows.
            # Deductions precede the first items, avoiding a detached details-only page.
            items = str(row['PRODUTOS']).split('\n')
            chunks = [items[i:i+5] for i in range(0, len(items), 5)]
            for index, chunk in enumerate(chunks):
                products = ([p(' · '.join(details), SMALL), Spacer(1, 5)] if index == 0 else []) + [p('\n'.join(chunk))]
                numbers = [p(row[key]*100 if key == 'Margem %' and row[key] is not None else row[key], NUMBER) for key in financial] if index == 0 else [p('') for _ in financial]
                label = identity if index == 0 else 'NF ' + str(row['NF']) + ' / ' + str(row['SÉRIE']) + '\nContinuação'
                data.append([p(label), products] + numbers)
        number_widths = [82 if key == 'Margem de contribuição' else 65 for key in financial]
        story.append(table(data, [90, width-90-sum(number_widths)] + number_widths, repeat=2))
    return report.build(story)
