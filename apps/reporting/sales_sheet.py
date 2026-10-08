"""One column definition shared by headings, totals and sale cells."""
from django.db.models import Count, Q

OPTIONAL=[('discount','Desconto'),('shipping_received','Frete recebido'),('revenue_adjustment','Ajuste receita'),
          ('shipping_paid','Frete pago'),('fees','Taxas'),('extra_costs_total','Extras / MDR'),
          ('difal','DIFAL'),('commission','Comissão'),('other_costs','Outros custos')]

def columns(user,rows):
    present=rows.aggregate(**{key:Count('pk',filter=~Q(**{key:0})) for key,_ in OPTIONAL})
    result=[('revenue','Receita')]
    if user.has_perm('core.view_costs'):result.append(('cmv','CMV histórico'))
    result += [(key,label) for key,label in OPTIONAL if present[key]]
    result.append(('tax_amount','Imposto'))
    if user.has_perm('core.view_margins'):result += [('contribution','Contribuição'),('margin','Margem')]
    return [{'key':key,'label':label,'percent':key=='margin'} for key,label in result]

def cells(source,cols):
    result=[]
    for col in cols:
        if isinstance(source,dict):value=source.get(col['key'])
        elif col['key'] in ('contribution','margin') and source.status!='CONFIRMED':value=None
        elif col['key']=='cmv' and source.status=='DRAFT':value=None
        else:value=getattr(source,'margin_percent' if col['key']=='margin' else col['key'])
        result.append(dict(col,value=value,negative=value is not None and value<0))
    return result

def decorate(groups,cols,rows):
    for group in groups:
        group['total_cells']=cells(group['totals'],cols)
        for sale in group['rows']:sale.report_cells=cells(sale,cols)
