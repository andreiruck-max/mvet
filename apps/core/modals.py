"""Explicit quick-action policy; business views/services keep their own permissions."""
import re
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from django.shortcuts import render
from django.urls import get_resolver
from django.urls.resolvers import URLResolver, RoutePattern
from django.utils.http import url_has_allowed_host_and_scheme

QUICK_ACTIONS = frozenset({
    'bling_detail', 'bling_purchase_detail', 'purchase_detail',
    'financial_transfer', 'financial_account_entry', 'financial_account_new', 'financial_account_edit',
    'financial_title_new', 'financial_title_edit',
    'financial_settlement_form', 'financial_due_payment',
    'expense_new', 'expense_edit',
    'expense_category_new', 'expense_category_edit', 'expense_rule_new', 'expense_rule_edit',
    'commission_action', 'commission_schedule', 'commission_payment_new',
    'crm_new', 'crm_edit', 'crm_interaction', 'crm_state', 'crm_decide',
    'product_new', 'product_edit', 'product_count', 'product_pricing', 'operation_new',
    'supplier_new', 'supplier_edit',
})


# POST-only services stay POST-only; they may receive forms from an embedded action.
MODAL_POST_ACTIONS = frozenset({'financial_settle','bling_alias','bling_decision','bling_purchase_refresh','bling_purchase_decision','purchase_confirm','purchase_receive'})

def is_modal(request):
    match = request.resolver_match
    return request.GET.get('_modal') == '1' and match and match.url_name in QUICK_ACTIONS | MODAL_POST_ACTIONS


@lru_cache(maxsize=1)
def action_patterns():
    result = []
    def walk(patterns, prefix=''):
        for item in patterns:
            if not isinstance(item.pattern, RoutePattern):
                continue
            route = prefix + item.pattern._route
            if isinstance(item, URLResolver):
                walk(item.url_patterns, route)
            elif item.name in QUICK_ACTIONS:
                parts = re.split(r'(<[^>]+>)', '/' + route)
                result.append('^' + ''.join(('[0-9]+' if p.startswith('<int:') else '[^/]+') if p.startswith('<') else re.escape(p) for p in parts) + '$')
    walk(get_resolver().url_patterns)
    return result


def context(request):
    return {'modal_mode': bool(is_modal(request)), 'action_patterns': action_patterns()}


class ActionModalMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not is_modal(request) or not request.user.is_authenticated:
            return response
        if response.status_code in (301, 302, 303):
            target = response.get('Location', '')
            if url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
                if request.method == 'POST' and request.resolver_match.url_name not in {'bling_alias','bling_purchase_refresh'} and not (request.resolver_match.url_name == 'bling_purchase_detail' and '/compras/' in target) and not target.split('?')[0].rstrip('/') == request.path.rstrip('/'):
                    # Leave Django messages for the origin page. Never replay a POST.
                    response = render(request, 'core/action_complete.html')
                else:
                    # E.g. a title backed by an expense routes to its expense editor.
                    parsed = urlsplit(target)
                    query = dict(parse_qsl(parsed.query)); query['_modal'] = '1'
                    response['Location'] = urlunsplit(parsed._replace(query=urlencode(query)))
        # Only explicitly allowed actions can be embedded, and only on the same origin.
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Cache-Control'] = 'no-store'
        return response
