"""Authorized report projections shared by HTML and file exports."""
from dataclasses import dataclass, field
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from apps.core.services import require
from . import forms, selectors


@dataclass
class Dataset:
    title: str
    headers: list
    rows: list
    notes: str = ''
    totals: dict = field(default_factory=dict)
    cash: list = field(default_factory=list)


def metrics_for(user, metrics):
    keys = ['name', 'id', 'count', 'products_amount', 'discount', 'shipping_received', 'revenue', 'ticket']
    if user.has_perm('core.view_costs'): keys += ['cmv']
    if user.has_perm('core.view_margins'): keys += ['contribution', 'margin', 'shipping_paid', 'fees', 'extra_costs_total', 'tax_amount', 'difal', 'commission', 'other_costs']
    return {key: metrics[key] for key in keys if key in metrics}


def bound(rows):
    if rows.count() > 10000:
        raise ValidationError('O relatório ultrapassa 10.000 registros. Reduza o período ou os filtros; nenhum registro foi omitido.')
    return rows


def sales_dataset(user, d, *, page_rows=None):
    require(user, 'core.view_sales_report')
    all_rows=selectors.sale_rows(d)
    rows = (bound(all_rows) if page_rows is None else page_rows).prefetch_related('items__product')
    costs, margins = user.has_perm('core.view_costs'), user.has_perm('core.view_margins')
    headers = ['DATA','NF','VALOR','DESCONTO','FRETE RECEBIDO','TOTAL','FRETE PAGO','DIF FRETE']
    if costs: headers += ['CMV histórico']
    if margins: headers += ['Margem antes de tributos e taxas']
    headers += ['SIMPLES','TAXAS']
    if margins: headers += ['Margem de contribuição']
    headers += ['PRODUTOS','SÉRIE','CANAL','ESTOQUE','SITUAÇÃO','EXTRAS / MDR','DIFAL','COMISSÃO','OUTROS CUSTOS']
    if margins: headers += ['Margem %','Alerta']
    values = []
    for sale in rows:
        confirmed = sale.status == 'CONFIRMED'
        row = [sale.date,sale.invoice_number,sale.products_amount,sale.discount,sale.shipping_received,sale.revenue,sale.shipping_paid,sale.shipping_received-sale.shipping_paid]
        if costs: row += [sale.cmv if sale.status != 'DRAFT' else None]
        if margins: row += [sale.revenue-sale.cmv-sale.shipping_paid if confirmed else None]
        row += [sale.tax_amount if sale.status != 'DRAFT' else None,sale.fees]
        if margins: row += [sale.contribution if confirmed else None]
        row += [' + '.join(f'{i.quantity} × {i.name_snapshot or i.product.name}' for i in sale.items.all()),sale.invoice_series,str(sale.channel),str(sale.location),sale.get_status_display(),sale.extra_costs_total,sale.difal,sale.commission,sale.other_costs]
        if margins: row += [sale.margin_percent/100 if confirmed and sale.margin_percent is not None else None,sale.margin_label if confirmed else 'Fora do resultado']
        values.append(row)
    return Dataset('Vendas', headers, values, 'CMV histórico preservado. Totais consideram somente vendas confirmadas. EBITDA/LUCRO da planilha foram substituídos por margens com definição correta.', metrics_for(user, selectors.sales_summary(all_rows)))


def build(kind, user, query):
    from apps.finance.forms import CashForm, FilterForm as TitlesForm
    from apps.expenses.forms import FilterForm as ExpensesForm
    from apps.purchases.forms import FilterForm as PurchasesForm
    form_class = {'sales':forms.SalesForm,'dashboard':forms.PeriodForm,'dre':forms.PeriodForm,'payables':forms.PayablesForm,'cash':CashForm,'titles':TitlesForm,'expenses':ExpensesForm,'purchases':PurchasesForm}.get(kind)
    permissions = {'sales':'view_sales_report','dashboard':'view_dashboard','dre':'view_dre','payables':'view_finance','cash':'view_finance','titles':'operate_finance','expenses':'view_expense_reports','purchases':'view_purchase_reports','stock':'view_stock'}
    if kind not in permissions: raise PermissionDenied
    if kind == 'titles' and user.has_perm('core.view_finance'): pass
    else: require(user,'core.'+permissions[kind])
    d = {}
    if form_class:
        form = form_class(query or {'period':'month'})
        if not form.is_valid(): raise ValidationError('; '.join(f'{key}: {", ".join(errors)}' for key,errors in form.errors.items()))
        d = form.cleaned_data
    if kind == 'sales': result = sales_dataset(user,d)
    elif kind == 'dashboard':
        rows = [metrics_for(user,x) for x in selectors.channel_summary(d)]
        keys = ['name','count','products_amount','discount','shipping_received','revenue','ticket']
        headers = ['Canal','Vendas','Produtos','Desconto','Frete recebido','Receita operacional','Ticket médio']
        if user.has_perm('core.view_costs'): keys += ['cmv']; headers += ['CMV']
        if user.has_perm('core.view_margins'): keys += ['contribution','margin']; headers += ['Contribuição','Margem (pontos percentuais)']
        result = Dataset('Faturamento por canal',headers,[[r.get(k) for k in keys] for r in rows],totals=metrics_for(user,selectors.sales_summary(selectors.sale_rows(d))))
    elif kind == 'stock':
        from apps.inventory.selectors import catalog
        result = Dataset('ESTOQUE MVET',['SKU','PRODUTO','QTD','UNIDADE'],[],'Posição atual. Kits virtuais: quantidade disponível pelos componentes, sem estoque próprio.')
        costs = user.has_perm('core.view_costs')
        if costs: result.headers = ['SKU','PRODUTO','QTD','CUSTO','VALOR TOTAL','UNIDADE']
        rows = bound(catalog(query)).prefetch_related('balances__location','components__component')
        for p in rows:
            if p.kind == 'KIT':
                parts = list(p.components.all()); qty = min((i.component.quantity//i.quantity for i in parts),default=0); cost = sum((i.component.average_cost*i.quantity for i in parts),Decimal(0))
            else: qty,cost=p.quantity,p.average_cost
            result.rows.append([p.sku,p.name,qty]+([cost,p.value if p.kind != 'KIT' else None] if costs else [])+[p.unit])
        # Local balances are a separate sheet; never infer Full from a global total.
        result.locations = Dataset('Estoque por local',['SKU','PRODUTO','LOCAL','QTD'],[[p.sku,p.name,str(b.location),b.quantity] for p in rows for b in p.balances.all()])
    elif kind == 'cash':
        from apps.finance.selectors import daily_cash
        rows,unallocated = daily_cash(d['start'],d['end'],d['account'].pk if d.get('account') else None)
        if len(rows)>10000: raise ValidationError('Reduza o período ou selecione uma conta (máximo 10.000 posições).')
        result = Dataset('Fluxo de Caixa',['Data','Conta','Saldo inicial','Entradas','Saídas','Saldo final','Projetado'],[[r['date'],str(r['account']),r['initial'],r['credits'],r['debits'],r['final'],r['projected']] for r in rows],f'Pendências sem conta fora da projeção: pagar R$ {unallocated["pay"]:.2f}; receber R$ {unallocated["receive"]:.2f}.',cash=rows)
    elif kind == 'titles':
        from apps.finance.selectors import titles
        result = Dataset('Contas a pagar e receber',['Tipo','Descrição','Favorecido','Vencimento','Valor','Baixado','Pendente','Situação','Conta prevista'],[[t.get_direction_display(),t.description,t.counterparty,t.due_date,t.amount,t.settled,t.remaining,t.display_status,str(t.account or '')] for t in bound(titles(d))])
    elif kind == 'expenses':
        from apps.expenses.selectors import expenses
        def historical_category(e):
            path=e.category_snapshot.get('path',[])
            return f"{path[-1]['code']} · {path[-1]['name']}" if path else 'A classificar'
        result = Dataset('Despesas',['Competência','Descrição','Favorecido','Categoria','Valor','Vencimento','Situação'],[[e.competence,e.description,e.counterparty,historical_category(e),e.amount,e.title.due_date,e.title.display_status if e.status=='ACTIVE' else 'Cancelada'] for e in bound(expenses(d))])
    elif kind in ('purchases','payables'):
        from apps.purchases.selectors import purchases
        from apps.purchases.models import PurchaseInstallment
        if kind == 'purchases':
            ids = bound(purchases(d)).values('pk')
            rows = PurchaseInstallment.objects.filter(purchase_id__in=ids).select_related('purchase__supplier','financial_title').prefetch_related('purchase__items__product','purchase__installments')
        else:
            rows = PurchaseInstallment.objects.filter(pk__in=bound(selectors.payables(d)).values('purchase_installment_id')).select_related('purchase__supplier','financial_title').prefetch_related('purchase__items__product','purchase__installments')
        result = Dataset('Compras',['DATA COMPRA','NF','FORNECEDOR','PARCELA','VCTO','VALOR','PRODUTOS','SITUAÇÃO','PENDENTE'],[],'Uma linha por parcela; não somar o valor total da compra repetidamente.')
        for i in bound(rows).order_by('due_date','pk'):
            p=i.purchase; result.rows.append([p.date,p.document,str(p.supplier),f'{i.number}/{len(p.installments.all())}',i.due_date,i.amount,' + '.join(f'{j.quantity} × {j.name_snapshot or j.product.name}' for j in p.items.all()),i.display_status,i.remaining])
        if kind=='purchases':
            for p in purchases(d).filter(installments__isnull=True).prefetch_related('items__product'):
                result.rows.append([p.date,p.document,str(p.supplier),'Sem parcelas',None,p.total,' + '.join(f'{j.quantity} × {j.name_snapshot or j.product.name}' for j in p.items.all()),p.get_status_display(),None])
            if len(result.rows)>10000: raise ValidationError('Reduza os filtros (máximo 10.000 linhas).')
    else:
        r=selectors.dre(d);s=r['sales']
        data=[('Receita bruta',s['products_amount']),('Descontos',-s['discount']),('Frete recebido',s['shipping_received']),('Receita operacional',s['revenue']),('CMV',-s['cmv'])]
        for k,label in [('shipping_paid','Frete pago'),('fees','Taxas'),('extra_costs_total','Extras / MDR'),('tax_amount','Imposto'),('difal','DIFAL'),('commission','Comissão'),('other_costs','Outros custos')]:data.append((label,-s[k]))
        data += [('Margem de contribuição',s['contribution'])]
        data += [('Despesa operacional · '+g['label'],-g['amount']) for g in r['groups'] if g['nature']=='OPERATING']
        if not r['channel_only']:data += [('EBITDA gerencial',r['ebitda'])]
        data += [('Despesa financeira · '+g['label'],-g['amount']) for g in r['groups'] if g['nature']=='FINANCIAL']
        data += [('Receitas financeiras adicionais',r['financial']['income']),('Despesas financeiras adicionais',-r['financial']['expense'])]
        if not r['channel_only']:data += [('Resultado gerencial',r['result'])]
        pending=f" Resultado PARCIAL: despesas a classificar R$ {r['expenses']['NONE']:.2f}; títulos a conferir R$ {r['financial']['unresolved']:.2f}; abatimentos R$ {r['financial']['discounts']:.2f}. Não incluídos automaticamente no resultado."
        result=Dataset('DRE gerencial',['Descrição','Valor'],data,'Regime de competência. Sem depreciação/amortização.'+(pending if r['provisional'] else '')+(' Canal: despesas corporativas sem rateio; resultado da empresa não calculado.' if r['channel_only'] else ''))
    if form_class:
        labels=[]
        for key,value in d.items():
            if value not in (None,'') and key not in ('period','sort'): labels.append(f'{form.fields[key].label}: {value}')
        result.notes='; '.join(labels)+'. '+result.notes
    return result
