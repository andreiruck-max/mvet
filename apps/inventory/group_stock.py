"""Read-only physical stock in one shared depot; never a valuation for a sale."""
from dataclasses import dataclass
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Case, Exists, F, OuterRef, When
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_safe

from apps.accounts.models import UserCompanyAccess
from apps.core.models import Company
from apps.products.models import Product
from .models import StockBalance, StockLocation
from .selectors import order_by_sku, search_products


@dataclass(frozen=True)
class OwnerColumn:
    company: Company
    costs: bool


def stock_columns(user, scope):
    if (not getattr(settings, 'COMPANY_CONTEXT_ENABLED', False) or not scope or not scope.group
            or not user.is_authenticated or not user.is_active):
        return []
    if user.is_superuser:
        # Inactivation prevents new operations; it does not erase existing stock.
        return [OwnerColumn(company, True) for company in Company.objects.order_by('pk')]
    grants = UserCompanyAccess.objects.select_related('company').filter(user=user, active=True,
        can_view_group=True, company__active=True, company_id__in=scope.company_ids).order_by('company_id')
    columns = []
    for grant in grants:
        if grant.company_id == 1 and grant.inherit_legacy:
            # Evaluate the inherited *individual* permission, including explicit
            # denials. The original user's read-only group context stays intact.
            legacy = get_user_model().objects.get(pk=user.pk)
            stock, costs = legacy.has_perm('core.view_stock'), legacy.has_perm('core.view_costs')
        else:
            stock, costs = (grant.rules.get(code) is True for code in ('core.view_stock','core.view_costs'))
        if stock:
            columns.append(OwnerColumn(grant.company, costs))
    return columns


class PositionFilter(forms.Form):
    location = forms.ModelChoiceField(label='Depósito', queryset=StockLocation.objects.order_by('-active','name','pk'),
                                      empty_label=None)
    q = forms.CharField(label='SKU ou nome', max_length=240, required=False)
    position = forms.ChoiceField(label='Produtos', choices=[
        ('moving','Com saldo em alguma empresa'), ('all','Todos os produtos físicos'),
    ])


def _position_page(columns, location, query, position, page_number):
    owner_ids = [column.company.pk for column in columns]
    cost_ids = [column.company.pk for column in columns if column.costs]
    balances = StockBalance.objects.filter(location=location,company_id__in=owner_ids)
    products = search_products(Product.objects.filter(kind='SIMPLE'),query)
    if position == 'moving':
        # +2 / -2 is relevant even when the signed physical total is zero.
        products = products.filter(Exists(balances.filter(product_id=OuterRef('pk')).exclude(quantity=0)))
    products = order_by_sku(products).values('id','sku','name','unit','active')
    page = Paginator(products,50).get_page(page_number)
    items = list(page.object_list)
    # Sum exactly the same owner cells we display (one DB read for the whole page).
    cells = balances.filter(product_id__in=[row['id'] for row in items]).annotate(
        visible_cost=Case(When(company_id__in=cost_ids,then=F('average_cost')),
                          default=None,output_field=StockBalance._meta.get_field('average_cost'))
    ).values_list('product_id','company_id','quantity','visible_cost')
    by_key = {(pid, cid):(quantity, cost) for pid,cid,quantity,cost in cells}
    for row in items:
        holdings = [by_key.get((row['id'],cid),(Decimal('0'),None)) for cid in owner_ids]
        row['cells'] = [dict(quantity=q, cost=c, show_cost=col.costs) for (q,c),col in zip(holdings,columns)]
        row['total'] = sum((q for q,_ in holdings), Decimal('0'))
    page.object_list = items
    return page


@login_required
@require_safe
def group_stock(request):
    if not getattr(settings,'COMPANY_CONTEXT_ENABLED',False):
        raise Http404
    columns = stock_columns(request.user,getattr(request,'company_scope',None))
    if not columns:
        raise PermissionDenied
    location = StockLocation.objects.order_by('-active','name','pk').first()
    data = request.GET.copy()
    if location:
        data.setdefault('location',str(location.pk))
    data.setdefault('position','moving')
    form = PositionFilter(data)
    page = None
    if location and form.is_valid():
        values = form.cleaned_data
        page = _position_page(columns,values['location'],values['q'],values['position'],request.GET.get('page'))
    complete = request.user.is_superuser or not Company.objects.exclude(pk__in=[c.company.pk for c in columns]).exists()
    return render(request,'inventory/group_stock.html',dict(columns=columns,form=form,page=page,
                  complete=complete,has_location=bool(location),back_url=reverse('company_context')))
