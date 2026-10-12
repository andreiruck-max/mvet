"""Presentation and starter profiles; authorization stays in domain services."""
GROUPS = [
 ('Comercial e CRM', ['operate_crm','view_own_commissions','manage_commissions']),
 ('Vendas', ['view_sales','operate_sales','confirm_sales','cancel_sales','view_sales_report']),
 ('Estoque e produtos', ['view_stock','operate_stock','manage_products','remove_products','manage_stock_catalogs','transfer_stock','adjust_stock','receive_stock','fraction_stock','adjust_stock_cost','reverse_stock']),
 ('Compras e fornecedores', ['operate_purchases','manage_suppliers','confirm_purchases','receive_purchases','cancel_purchases','view_purchase_reports']),
 ('Financeiro', ['view_finance','operate_finance','manage_financial_accounts','create_financial_titles','schedule_financial_titles','pay_titles','receive_titles','transfer_finance','reverse_finance','cancel_financial_titles']),
 ('Despesas', ['operate_expenses','cancel_expenses','reclassify_expenses','manage_recurrence','view_expense_reports']),
 ('Indicadores e informações sensíveis', ['view_dashboard','view_costs','view_margins','view_dre','view_auditlog']),
 ('Integração Bling', ['review_bling','fetch_bling','map_bling_products','approve_bling']),
 ('Configurações', ['manage_configuration','manage_channels','manage_taxes','retroactive_taxes','manage_alerts','manage_expense_rules']),
 ('Exportações', ['export_dashboard','export_sales','export_stock','export_purchases','export_finance','export_expenses','export_dre']),
]
SENSITIVE = {'view_costs','view_margins','view_dre','view_finance','view_auditlog','manage_configuration','retroactive_taxes','manage_commissions','operate_purchases','view_purchase_reports','operate_expenses','view_expense_reports','operate_finance'}
DEPENDENCIES = {}
for action in ('confirm_sales','cancel_sales'):
 DEPENDENCIES[action] = ['operate_sales']
for action in ('manage_products','remove_products','manage_stock_catalogs','transfer_stock','adjust_stock','receive_stock','fraction_stock','adjust_stock_cost','reverse_stock'):
 DEPENDENCIES[action] = ['operate_stock']
for action in ('receive_stock','adjust_stock_cost','reverse_stock'):
 DEPENDENCIES[action] += ['view_costs']
for action in ('manage_suppliers','confirm_purchases','receive_purchases','cancel_purchases'):
 DEPENDENCIES[action] = ['operate_purchases']
for action in ('manage_financial_accounts','create_financial_titles','schedule_financial_titles','pay_titles','receive_titles','transfer_finance','reverse_finance','cancel_financial_titles'):
 DEPENDENCIES[action] = ['operate_finance']
DEPENDENCIES['manage_financial_accounts'] += ['view_finance']
for action in ('cancel_expenses','reclassify_expenses','manage_recurrence'):
 DEPENDENCIES[action] = ['operate_expenses']
for action in ('fetch_bling','map_bling_products','approve_bling'):
 DEPENDENCIES[action] = ['review_bling']
DEPENDENCIES['retroactive_taxes'] = ['manage_taxes']
for export, read in [('dashboard','view_dashboard'),('sales','view_sales_report'),('stock','view_stock'),('purchases','view_purchase_reports'),('finance','view_finance'),('expenses','view_expense_reports'),('dre','view_dre')]:
 DEPENDENCIES['export_'+export] = [read]

PROFILES = {
 'stock_read': {'label':'Consulta de estoque', 'description':'Quantidades e preços de venda, sem custos, bancos ou resultados.', 'codes':['view_stock']},
 'commercial': {'label':'Comercial', 'description':'Carteira CRM, estoque e vendas. Sem cancelamentos, custos, bancos ou resultados.', 'codes':['operate_crm','view_stock','view_sales','operate_sales','confirm_sales']},
 'stock': {'label':'Operação de estoque', 'description':'Produtos e transferências. Entradas com custo e estornos ficam bloqueados.', 'codes':['view_stock','operate_stock','manage_products','transfer_stock']},
 'purchases': {'label':'Compras', 'description':'Fornecedores, compras e recebimento; envolve preços de aquisição. Sem pagar ou cancelar.', 'codes':['operate_purchases','manage_suppliers','confirm_purchases','receive_purchases','view_purchase_reports','view_stock']},
 'finance': {'label':'Financeiro', 'description':'Saldos, títulos, pagamentos e despesas. Sem estornos, transferências, DRE ou exportação.', 'codes':['view_finance','operate_finance','create_financial_titles','schedule_financial_titles','pay_titles','operate_expenses']},
 'none': {'label':'Sem acesso aos módulos', 'description':'Desmarca todas as permissões. A conta continua ativa até desmarcar Usuário ativo.', 'codes':[]},
}


def permission_groups(form):
    available = {str(option.data['value']).removeprefix('core.'):option for option in form['permissions']}
    labels = {code: str(option.choice_label) for code, option in available.items()}
    result = []
    for title, codes in GROUPS + [('Outras permissões', list(available))]:
        items = []
        for code in codes:
            option = available.pop(code, None)
            if option is None: continue
            items.append({'option':option, 'sensitive':code in SENSITIVE,
                          'requires':', '.join(labels.get(dep, dep) for dep in DEPENDENCIES.get(code, [])),
                          'requires_codes':['core.'+dep for dep in DEPENDENCIES.get(code, [])]})
        if items: result.append({'title':title, 'items':items})
    return result
