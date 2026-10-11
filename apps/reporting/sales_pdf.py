"""Channel sections, one row per invoice, deductions alongside its products."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak


def render(dataset, company):
    out=BytesIO();page=landscape(A4);width=page[0]-48
    document=SimpleDocTemplate(out,pagesize=page,leftMargin=24,rightMargin=24,topMargin=28,bottomMargin=30,title='Relatório de vendas',author=company)
    normal=ParagraphStyle('normal',fontName='Helvetica',fontSize=8,leading=11)
    number=ParagraphStyle('number',parent=normal,alignment=2)
    white=ParagraphStyle('white',parent=normal,textColor=colors.white,fontName='Helvetica-Bold')
    heading=ParagraphStyle('heading',parent=normal,fontName='Helvetica-Bold',fontSize=15,leading=20)
    def fmt(value):
        if value is None:return '—'
        if isinstance(value,date):return value.strftime('%d/%m/%Y')
        if isinstance(value,Decimal):return f'{value:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
        return str(value)
    def p(value,style=normal):
        content=escape(fmt(value)).replace('\n','<br/>')
        if isinstance(value,Decimal) and value<0:content='<font color="#bb2020">'+content+'</font>'
        return Paragraph(content,style)
    def table(data,widths):
        obj=LongTable(data,colWidths=widths,repeatRows=1,splitInRow=0,hAlign='LEFT')
        obj.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#20234c')),
          ('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f2f6')]),
          ('GRID',(0,0),(-1,-1),.35,colors.HexColor('#c1c6d0')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        return obj
    margins='contribution' in dataset.totals;costs='cmv' in dataset.totals
    keys=['count','revenue']+(['cmv'] if costs else [])+(['tax_amount','contribution','margin'] if margins else [])
    labels={'count':'Vendas','revenue':'Receita','cmv':'CMV','tax_amount':'Imposto','contribution':'Contribuição','margin':'Margem %'}
    story=[p(company,heading),p('Relatório de vendas · resumo',heading),p(dataset.notes),Spacer(1,12)]
    summary=[[p('Canal',white)]+[p(labels[k],white) for k in keys]]
    for name,totals in [('Total da empresa',dataset.totals)]+[(g.notes,g.totals) for g in dataset.groups]:
        summary.append([p(name)]+[p(totals.get(k),number) for k in keys])
    story.append(table(summary,[width*.34]+[width*.66/len(keys)]*len(keys)))
    story.append(p('Valores em R$. Totais somente de vendas confirmadas. Rascunhos e cancelamentos, quando selecionados, ficam identificados e não compõem os totais.'))
    for group in dataset.groups:
        story.extend([PageBreak(),p(group.notes,heading),p(f"{group.totals['count']} vendas confirmadas · Receita R$ {fmt(group.totals['revenue'])}"),Spacer(1,10)])
        details_totals=[]
        for key,label in [('discount','Desconto'),('shipping_received','Frete recebido'),('shipping_paid','Frete pago'),('fees','Taxas'),('extra_costs_total','Extras / MDR'),('difal','DIFAL'),('commission','Comissão'),('other_costs','Outros custos'),('revenue_adjustment','Ajuste de receita')]:
            if group.totals.get(key):details_totals.append(label+': R$ '+fmt(group.totals[key]))
        if details_totals:story.extend([p('Totais do canal · '+' · '.join(details_totals)),Spacer(1,8)])
        financial=['TOTAL']+(['CMV histórico'] if costs else [])+['SIMPLES']+(['Margem de contribuição','Margem %'] if margins else [])
        labels2={'TOTAL':'Receita','SIMPLES':'Imposto','Margem de contribuição':'Contribuição','CMV histórico':'CMV'}
        data=[[p(v,white) for v in ['Data / NF','Produtos / quantidades e deduções']+[labels2.get(k,k) for k in financial]]]
        for values in group.rows:
            row=dict(zip(group.headers,values))
            identity=fmt(row['DATA'])+'\nNF '+str(row['NF'])+' / '+str(row['SÉRIE'])
            if row['SITUAÇÃO']!='Confirmada':identity+='\n'+row['SITUAÇÃO']
            details=['Produtos: R$ '+fmt(row['VALOR'])]
            for key in ['DESCONTO','FRETE RECEBIDO','FRETE PAGO','TAXAS','EXTRAS / MDR','DIFAL','COMISSÃO','OUTROS CUSTOS','AJUSTE GERENCIAL DA RECEITA']:
                if row[key]:details.append(key.title()+': R$ '+fmt(row[key]))
            details.append('Estoque: '+str(row['ESTOQUE']))
            products=str(row['PRODUTOS']).split('\n')
            data.append([p(identity),p(products[0])]+[p(row[key]*100 if key=='Margem %' and row[key] is not None else row[key],number) for key in financial])
            for product in products[1:]:
                data.append([p('NF '+str(row['NF'])+' (cont.)'),p(product)]+[p('') for key in financial])
            data.append([p('NF '+str(row['NF'])+' · detalhes'),p(' · '.join(details))]+[p('') for key in financial])
        numeric_width=65
        story.append(table(data,[92,width-92-len(financial)*numeric_width]+[numeric_width]*len(financial)))
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.drawRightString(page[0]-24,14,f'Página {doc.page}')
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
