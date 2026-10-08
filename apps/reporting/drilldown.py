"""Master-only DRE source navigation; never mutates accounting records."""
from decimal import Decimal
from urllib.parse import urlencode
from django.core import signing
from django.http import Http404
from django.urls import reverse
from apps.expenses.models import Expense
from apps.purchases.models import PurchaseItem
from apps.inventory.models import StockMovement
from apps.finance.models import FinancialTitle, FinancialOperation
from . import selectors

SALES=[('products_amount','Receita bruta · produtos'),('discount','(−) Descontos'),
 ('shipping_received','(+) Frete recebido'),('revenue_adjustment','(+/−) Ajuste gerencial da receita'),
 ('revenue','Receita operacional'),('cmv','(−) CMV histórico'),('shipping_paid','(−) Frete das vendas'),
 ('fees','(−) Taxas de canal'),('extra_costs_total','(−) Taxas extras / MDR'),('commission','(−) Comissão'),
 ('tax_amount','(−) Impostos sobre vendas'),('difal','(−) DIFAL'),('other_costs','(−) Outros custos variáveis'),
 ('contribution','Margem de contribuição')]
SALT='dre-source-v1'

def url(spec,data):
    params={'start':data['start'].isoformat(),'end':data['end'].isoformat(),'source':signing.dumps(spec,salt=SALT,compress=True)}
    if data.get('channel'):params['channel']=data['channel'].pk
    return reverse('dre_sources')+'?'+urlencode(params)

def lines(report,data,master):
    result=[]
    def add(label,value,spec=None,total=False):
        result.append(dict(label=label,value=value,total=total,url=url(dict(spec,label=label),data) if master and spec else None))
    for key,label in SALES:add(label,report['sales'][key],{'kind':'sale','field':key},key in ('revenue','contribution'))
    add('(−) Despesas operacionais da empresa',report['expenses']['OPERATING'],{'kind':'nature','nature':'OPERATING'})
    if not report['channel_only']:add('EBITDA gerencial',report['ebitda'],total=True)
    add('(−) Despesas financeiras por competência',report['expenses']['FINANCIAL'],{'kind':'nature','nature':'FINANCIAL'})
    add('(+) Receitas financeiras e juros adicionais',report['financial']['income'],{'kind':'financial','direction':'RECEIVE'})
    add('(−) Títulos financeiros e juros adicionais',report['financial']['expense'],{'kind':'financial','direction':'PAY'})
    if not report['channel_only']:add('Resultado gerencial antes de depreciação/amortização',report['result'],total=True)
    if master:
        for group in report['groups']:
            group['url']=url({'kind':group['source_kind'],'snapshot':group.get('snapshot'),'label':group['label']},data)
    return result

def sources(token,data):
    try:spec=signing.loads(token,salt=SALT)
    except signing.BadSignature:raise Http404('Origem inválida.')
    kind=spec.get('kind');rows=[]
    def add(date,origin,description,amount,route,pk):
        if amount:rows.append(dict(date=date,origin=origin,description=description,amount=amount,url=reverse(route,args=[pk])))
    dates=(data['start'],data['end'])
    if kind=='sale' and spec.get('field') in dict(SALES):
        for sale in selectors.sale_rows({**data,'status':'CONFIRMED'}):
            add(sale.date,'Venda '+sale.reference,spec['label'],getattr(sale,spec['field']),'sale_detail',sale.pk)
    elif kind in ('nature','expense','purchase','inventory'):
        nature=spec.get('nature')
        if kind in ('nature','expense'):
            qs=Expense.objects.filter(status='ACTIVE',competence__range=dates)
            qs=qs.filter(category_snapshot__nature=nature) if kind=='nature' else qs.filter(category_snapshot=spec['snapshot'])
            for row in qs:add(row.competence,'Despesa #'+str(row.pk),row.description,row.amount,'expense_detail',row.pk)
        if kind in ('nature','purchase'):
            qs=PurchaseItem.objects.filter(moves_stock=False,purchase__status__in=['ORDERED','RECEIVED'],purchase__date__range=dates).select_related('purchase','purchase__supplier')
            qs=qs.filter(category_snapshot__nature=nature) if kind=='nature' else qs.filter(category_snapshot=spec['snapshot'])
            for row in qs:add(row.purchase.date,'Compra '+row.purchase.document,str(row.purchase.supplier)+' · '+row.name_snapshot,row.nonstock_total,'purchase_detail',row.purchase_id)
        if kind=='inventory' or (kind=='nature' and nature=='OPERATING'):
            for row in StockMovement.objects.filter(operation__date__range=dates).exclude(cost_variance=0).select_related('operation','product','location'):
                add(row.operation.date,'Movimento #'+str(row.operation_id),str(row.product)+' · '+str(row.location),row.cost_variance,'operation_detail',row.operation_id)
    elif kind=='financial' and spec.get('direction') in ('PAY','RECEIVE'):
        direction=spec['direction']
        titles=FinancialTitle.objects.filter(status='OPEN',opening=False,source='manual',sale__isnull=True,purchase_installment__isnull=True,expense__isnull=True,date__range=dates,category='FINANCIAL',direction=direction)
        for row in titles:add(row.date,'Título #'+str(row.pk),row.description,row.amount,'financial_title',row.pk)
        ops=FinancialOperation.objects.filter(status='POSTED',date__range=dates).select_related('title','reversal_of__title')
        for row in ops:
            original=row if row.kind=='SETTLEMENT' else row.reversal_of if row.kind=='REVERSAL' else None
            if original and original.kind=='SETTLEMENT' and original.title and original.title.direction==direction:
                add(row.date,'Juros' if row.kind=='SETTLEMENT' else 'Estorno de juros',row.description,original.interest*(1 if row.kind=='SETTLEMENT' else -1),'financial_operation',row.pk)
    else:raise Http404('Origem inválida.')
    rows.sort(key=lambda row:(row['date'],row['origin']))
    return spec,rows,sum((row['amount'] for row in rows),Decimal(0))
