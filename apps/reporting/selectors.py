"""Read-only reports over historical sources; never derive accrual from cash."""
from decimal import Decimal
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from apps.sales.models import Sale
from apps.finance.models import FinancialTitle as Title, FinancialOperation as Operation
from apps.expenses.selectors import expense_report

ZERO=Decimal('0')
FIELDS=['products_amount','discount','shipping_received','cmv','shipping_paid','fees','extra_costs_total','tax_amount','difal','commission','other_costs']

def sale_rows(d):
    rows=Sale.objects.filter(date__range=(d['start'],d['end'])).select_related('channel','location')
    if d.get('channel'):rows=rows.filter(channel=d['channel'])
    if d.get('q'):rows=rows.filter(invoice_number__icontains=d['q'])
    status=d.get('status') or 'CONFIRMED'
    if status!='all':rows=rows.filter(status=status)
    return rows.order_by(d.get('sort') or '-date','-pk')

def metrics(values):
    result={f:values.get(f) or ZERO for f in FIELDS}
    result['count']=values.get('count',0)
    result['revenue']=result['products_amount']-result['discount']+result['shipping_received']
    result['contribution']=result['revenue']-sum((result[f] for f in FIELDS[3:]),ZERO)
    result['margin']=result['contribution']/result['revenue']*100 if result['revenue'] else None
    result['ticket']=result['revenue']/result['count'] if result['count'] else ZERO
    return result

def sales_summary(rows):
    return metrics(rows.filter(status='CONFIRMED').aggregate(**{f:Sum(f) for f in FIELDS},count=Count('pk')))

def channel_summary(d):
    rows=sale_rows({**d,'status':'CONFIRMED'}).order_by().values('channel_id','channel__name').annotate(**{f:Sum(f) for f in FIELDS},count=Count('pk'))
    return [{'name':r['channel__name'],'id':r['channel_id'],**metrics(r)} for r in rows.order_by('channel__name')]

def payables(d):
    rows=Title.objects.filter(purchase_installment__isnull=False,status='OPEN',due_date__range=(d['start'],d['end'])).select_related('account','purchase_installment__purchase__supplier')
    if d.get('supplier'):rows=rows.filter(purchase_installment__purchase__supplier=d['supplier'])
    if d.get('purchase_start'):rows=rows.filter(purchase_installment__purchase__date__gte=d['purchase_start'])
    if d.get('purchase_end'):rows=rows.filter(purchase_installment__purchase__date__lte=d['purchase_end'])
    status=d.get('status') or 'pending'
    if status=='paid':rows=rows.filter(settled=F('amount'))
    elif status in ['pending','overdue']:rows=rows.filter(settled__lt=F('amount'))
    if status=='overdue':rows=rows.filter(due_date__lt=timezone.localdate())
    return rows.order_by('due_date','pk')

def payable_totals(rows):
    result=rows.aggregate(total_amount=Sum('amount'),paid=Sum('settled'),pending=Sum(F('amount')-F('settled')))
    return dict(amount=result['total_amount'] or ZERO,paid=result['paid'] or ZERO,pending=result['pending'] or ZERO)

def financial_result(d):
    """Manual financial titles accrue on origin date, additional interest when assessed.
    Reversals negate additional interest on their own effective date. Principal
    linked to an expense/sale/purchase is never recognized a second time.
    Abatements are unresolved (may already be marketplace costs), not guessed.
    """
    titles=Title.objects.filter(status='OPEN',opening=False,source='manual',sale__isnull=True,purchase_installment__isnull=True,expense__isnull=True,date__range=(d['start'],d['end']))
    financial=titles.filter(category='FINANCIAL').aggregate(income=Sum('amount',filter=Q(direction='RECEIVE')),expense=Sum('amount',filter=Q(direction='PAY')))
    income=financial['income'] or ZERO;expense=financial['expense'] or ZERO
    ops=Operation.objects.filter(status='POSTED',date__range=(d['start'],d['end']))
    direct=ops.filter(kind='SETTLEMENT').aggregate(income=Sum('interest',filter=Q(title__direction='RECEIVE')),expense=Sum('interest',filter=Q(title__direction='PAY')),discount=Sum('discount'))
    reversals=ops.filter(kind='REVERSAL',reversal_of__kind='SETTLEMENT').aggregate(income=Sum('reversal_of__interest',filter=Q(reversal_of__title__direction='RECEIVE')),expense=Sum('reversal_of__interest',filter=Q(reversal_of__title__direction='PAY')),discount=Sum('reversal_of__discount'))
    income+=(direct['income'] or ZERO)-(reversals['income'] or ZERO)
    expense+=(direct['expense'] or ZERO)-(reversals['expense'] or ZERO)
    unresolved=titles.filter(category__in=['OTHER','OPERATING']).aggregate(value=Sum('amount'))['value'] or ZERO
    # Gross volume highlights corrections even if different abatements net to zero.
    discounts=(direct['discount'] or ZERO)+(reversals['discount'] or ZERO)
    return dict(income=income,expense=expense,unresolved=unresolved,discounts=discounts)

def dre(d):
    sales=sales_summary(sale_rows({**d,'status':'CONFIRMED'}))
    groups,expenses=expense_report({'start':d['start'],'end':d['end']})
    for group in groups:group['nature_label']={'OPERATING':'Operacional','FINANCIAL':'Financeira','NONE':'A classificar'}[group['nature']]
    financial=financial_result(d)
    provisional=bool(expenses['NONE'] or financial['unresolved'] or financial['discounts'])
    # A channel report has contribution only. Unassigned corporate expenses are
    # shown separately, never subtracted from each channel.
    ebitda=None if d.get('channel') else sales['contribution']-expenses['OPERATING']
    result=None if ebitda is None else ebitda-expenses['FINANCIAL']+financial['income']-financial['expense']
    return dict(sales=sales,groups=groups,expenses=expenses,financial=financial,ebitda=ebitda,result=result,provisional=provisional,channel_only=bool(d.get('channel')))
