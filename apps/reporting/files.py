"""Portable report serializers: typed XLSX (OOXML) and paginated PDF.

No private authoring runtime, Excel installation or commercial data templates
are required on the company computer. Only authorized Dataset projections enter.
"""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import re
from xml.etree.ElementTree import Element, SubElement, tostring, fromstring
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
METRICS={'count':'Vendas confirmadas','products_amount':'Valor dos produtos','discount':'Descontos','shipping_received':'Frete recebido','revenue':'Receita operacional','ticket':'Ticket médio','cmv':'CMV histórico','contribution':'Margem de contribuição','margin':'Margem (pontos percentuais)','shipping_paid':'Frete pago','fees':'Taxas','extra_costs_total':'Extras / MDR','tax_amount':'Imposto','difal':'DIFAL','commission':'Comissão','other_costs':'Outros custos'}


def column(index):
    result=''
    while index:
        index,rem=divmod(index-1,26);result=chr(65+rem)+result
    return result


def text(value):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))[:32767]


def cell(row, col, value, style=None):
    attrs={'r':f'{column(col)}{row.get("r")}'}
    if style is not None:attrs['s']=str(style)
    node=SubElement(row,'c',attrs)
    if value is None:return
    if isinstance(value,datetime):value=value.date()
    if isinstance(value,date):
        node.set('s','6' if style==1 else '3');SubElement(node,'v').text=str((value-date(1899,12,30)).days)
    elif isinstance(value,(int,Decimal)) and not isinstance(value,bool):
        if style is None:node.set('s','2')
        SubElement(node,'v').text=str(value)
    else:
        # inlineStr prevents =, +, -, @ user text becoming spreadsheet formulas.
        node.set('t','inlineStr');SubElement(SubElement(node,'is'),'t').text=text(value)


def sheet_xml(dataset, company, *, horizontal=False):
    root=Element('worksheet',xmlns=NS)
    view=SubElement(SubElement(root,'sheetViews'),'sheetView',workbookViewId='0',showGridLines='0')
    header=2 if horizontal or dataset.title in ('ESTOQUE MVET','Compras') else 4
    SubElement(view,'pane',ySplit=str(header),topLeftCell=f'A{header+1}',activePane='bottomLeft',state='frozen')
    cols=SubElement(root,'cols')
    count=len(dataset.headers)
    if horizontal:count=1+3*len({r['date'] for r in dataset.cash})
    for i in range(1,count+1):
        label=dataset.headers[i-1] if not horizontal and i<=len(dataset.headers) else ''
        width=40 if any(x in label.upper() for x in ['PRODUTO','DESCRI','FORNECEDOR','CATEGORIA']) else 20
        if dataset.title=='ESTOQUE MVET':width={'SKU':9.14,'PRODUTO':63,'QTD':11.425,'CUSTO':12.71,'VALOR TOTAL':12.71}.get(label,width)
        elif dataset.title=='Compras':width={'DATA COMPRA':14.855,'NF':8.71,'FORNECEDOR':40.57,'VCTO':11.425,'VALOR':13.855,'PRODUTOS':141.71}.get(label,width)
        elif dataset.title=='Vendas':width={'DATA':12,'NF':7.71,'VALOR':11.14,'DESCONTO':16.855,'FRETE RECEBIDO':16.855,'TOTAL':13.425,'FRETE PAGO':16.71,'DIF FRETE':15.57,'CMV histórico':12.285,'SIMPLES':15.71,'TAXAS':10.285}.get(label,width)
        if horizontal and i==1:width=32
        SubElement(cols,'col',min=str(i),max=str(i),width=str(width),customWidth='1')
    data=SubElement(root,'sheetData');merges=[]
    if horizontal:
        days=sorted({r['date'] for r in dataset.cash});accounts={r['account'].pk:str(r['account']) for r in dataset.cash}
        lookup={(r['account'].pk,r['date']):r for r in dataset.cash}
        row=SubElement(data,'row',r='1',ht='28',customHeight='1');cell(row,1,'Conta',1)
        for j,day in enumerate(days):
            col=2+j*3;cell(row,col,day,1);merges.append(f'{column(col)}1:{column(col+2)}1')
        row=SubElement(data,'row',r='2',ht='28',customHeight='1');cell(row,1,company,1)
        for j in range(len(days)):
            for offset,label in enumerate(['Entradas','Saídas','Saldo']):cell(row,2+j*3+offset,label,1)
        for i,(pk,name) in enumerate(accounts.items(),3):
            row=SubElement(data,'row',r=str(i));cell(row,1,name)
            for j,day in enumerate(days):
                r=lookup.get((pk,day))
                for offset,key in enumerate(['credits','debits','final']):cell(row,2+j*3+offset,r[key] if r else None)
    else:
        row=SubElement(data,'row',r='1',ht='26',customHeight='1');cell(row,1,dataset.title+' - '+company,4)
        if count>1:merges.append(f'A1:{column(count)}1')
        if header>2:
            row=SubElement(data,'row',r='2',ht='45',customHeight='1');cell(row,1,dataset.notes)
            if count>1:merges.append(f'A2:{column(count)}2')
        row=SubElement(data,'row',r=str(header),ht='38',customHeight='1')
        for i,label in enumerate(dataset.headers,1):cell(row,i,label,1)
        for r,values in enumerate(dataset.rows,header+1):
            height=min(409, max(30, max((len(str(v))//35+1)*14 for v in values)))
            row=SubElement(data,'row',r=str(r),ht=str(height),customHeight='1')
            for c,value in enumerate(values,1):
                style=5 if dataset.headers[c-1]=='Margem %' and value is not None else None
                cell(row,c,value,style)
        end=header+len(dataset.rows)
        if dataset.rows:SubElement(root,'autoFilter',ref=f'A{header}:{column(count)}{end}')
        if header==2:
            row=SubElement(data,'row',r=str(end+2),ht='45',customHeight='1');cell(row,1,dataset.notes)
            if count>1:merges.append(f'A{end+2}:{column(count)}{end+2}')
    if merges:
        node=SubElement(root,'mergeCells',count=str(len(merges)))
        for ref in merges:SubElement(node,'mergeCell',ref=ref)
    SubElement(root,'pageMargins',left='0.3',right='0.3',top='0.5',bottom='0.5',header='0.2',footer='0.2')
    SubElement(root,'pageSetup',orientation='landscape',paperSize='9',fitToWidth='1',fitToHeight='0')
    return tostring(root,encoding='utf-8',xml_declaration=True)


STYLES=f'''<styleSheet xmlns="{NS}"><numFmts count="3"><numFmt numFmtId="164" formatCode="#,##0.00####"/><numFmt numFmtId="165" formatCode="dd/mm/yyyy"/><numFmt numFmtId="166" formatCode="0.00%"/></numFmts><fonts count="3"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font><font><b/><sz val="14"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1B1C4A"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" applyFill="1" applyFont="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/><xf numFmtId="0" fontId="2" fillId="0" borderId="0" applyFont="1"/><xf numFmtId="166" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''


def xlsx(dataset, company):
    from .datasets import Dataset
    sheets=[(dataset, bool(dataset.cash))]
    if dataset.cash:sheets.append((Dataset('Caixa detalhado',dataset.headers,dataset.rows,dataset.notes),False))
    if hasattr(dataset,'locations'):sheets.append((dataset.locations,False))
    if dataset.totals:sheets.append((Dataset('Totais confirmados',['Indicador','Valor'],[(METRICS.get(k,k),v) for k,v in dataset.totals.items()]),False))
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        content=Element('Types',xmlns='http://schemas.openxmlformats.org/package/2006/content-types')
        SubElement(content,'Default',Extension='rels',ContentType='application/vnd.openxmlformats-package.relationships+xml')
        SubElement(content,'Default',Extension='xml',ContentType='application/xml')
        SubElement(content,'Override',PartName='/xl/workbook.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
        SubElement(content,'Override',PartName='/xl/styles.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml')
        workbook=Element('workbook',xmlns=NS);nodes=SubElement(workbook,'sheets')
        rels=Element('Relationships',xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        for i,(ds,horizontal) in enumerate(sheets,1):
            SubElement(nodes,'sheet',name=ds.title[:31],sheetId=str(i),attrib={f'{{{REL}}}id':f'rId{i}'})
            SubElement(rels,'Relationship',Id=f'rId{i}',Type=REL+'/worksheet',Target=f'worksheets/sheet{i}.xml')
            SubElement(content,'Override',PartName=f'/xl/worksheets/sheet{i}.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
            z.writestr(f'xl/worksheets/sheet{i}.xml',sheet_xml(ds,company,horizontal=horizontal))
        SubElement(rels,'Relationship',Id='styles',Type=REL+'/styles',Target='styles.xml')
        styles=fromstring(STYLES)
        # Style 6 preserves the date format and visual day header together.
        xfs=styles.find(f'{{{NS}}}cellXfs')
        dated=fromstring(tostring(xfs[1]));dated.set('numFmtId','165');dated.set('applyNumberFormat','1')
        xfs.append(dated);xfs.set('count',str(len(xfs)))
        if dataset.title=='Vendas':
            styles.find(f'{{{NS}}}fills')[2].find(f'{{{NS}}}patternFill/{{{NS}}}fgColor').set('rgb','FF00B0F0')
            styles.find(f'{{{NS}}}fonts')[1].find(f'{{{NS}}}color').set('rgb','FF000000')
        z.writestr('xl/styles.xml',tostring(styles));z.writestr('xl/workbook.xml',tostring(workbook));z.writestr('xl/_rels/workbook.xml.rels',tostring(rels));z.writestr('[Content_Types].xml',tostring(content))
        z.writestr('_rels/.rels',f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="book" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    return out.getvalue()


def pdf(dataset, company):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak
    out=BytesIO();page=landscape(A4)
    document=SimpleDocTemplate(out,pagesize=page,rightMargin=28,leftMargin=28,topMargin=35,bottomMargin=35,title=dataset.title,author=company)
    body=ParagraphStyle('body',fontName='Helvetica',fontSize=8,leading=11,wordWrap='CJK')
    heading=ParagraphStyle('heading',fontName='Helvetica-Bold',fontSize=14,leading=18)
    white=ParagraphStyle('white',parent=body,textColor=colors.white)
    story=[]
    def value(v):
        if v is None:return '-'
        if isinstance(v,date):return v.strftime('%d/%m/%Y')
        if isinstance(v,Decimal):return f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
        return str(v)
    def paragraph(v,style=body):return Paragraph(escape(value(v)),style)
    # Split wide reports into readable blocks, repeating identifying columns.
    indexes=list(range(len(dataset.headers)));blocks=[indexes] if len(indexes)<=8 else [[0,1]+indexes[i:i+6] for i in range(2,len(indexes),6)]
    for block_no,index in enumerate(blocks):
        if block_no:story.append(PageBreak())
        story += [paragraph(company,heading),paragraph(dataset.title+f' - bloco {block_no+1}/{len(blocks)}',heading),paragraph(dataset.notes),Spacer(1,12)]
        table_data=[[paragraph(dataset.headers[c],white) for c in index]]
        for row in dataset.rows:
            table_data.append([paragraph(row[c]*100 if dataset.headers[c]=='Margem %' and row[c] is not None else row[c]) for c in index])
        if len(table_data)==1:table_data.append([paragraph('Sem registros')]+[paragraph('') for _ in index[1:]])
        table=LongTable(table_data,colWidths=[(page[0]-56)/len(index)]*len(index),repeatRows=1,hAlign='LEFT',splitInRow=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1b1c4a')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f1f3f7')]),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(table)
    if dataset.totals:
        story += [Spacer(1,12),paragraph('Totais das vendas confirmadas',heading)]
        for k,v in dataset.totals.items():story.append(paragraph(f'{METRICS.get(k,k)}: {value(v)}'))
    if hasattr(dataset,'locations'):
        locations=dataset.locations
        story += [PageBreak(),paragraph('Estoque por local',heading),Spacer(1,12)]
        table=LongTable([[paragraph(v) for v in locations.headers]]+[[paragraph(v) for v in row] for row in locations.rows],colWidths=[90,360,220,page[0]-726],repeatRows=1,splitInRow=1)
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.HexColor('#f1f3f7'),colors.white])]))
        story.append(table)
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.drawRightString(page[0]-28,18,f'Página {doc.page}')
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
