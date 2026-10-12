from urllib.parse import urlsplit, urlencode
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from config.version import VERSION

SETTINGS_CAPABILITIES = ('manage_configuration','manage_channels','manage_taxes','manage_stock_catalogs','manage_expense_rules','manage_alerts','manage_commissions')


def can_manage_settings(user):
    return user.is_authenticated and any(user.has_perm('core.'+code) for code in SETTINGS_CAPABILITIES)


def safe_return(request, value):
    if not value or len(value) > 4000:
        return None
    if not url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return None
    parsed = urlsplit(value)
    if not parsed.path.startswith('/') or parsed.path.startswith('//'):
        return None
    path = parsed.path + ('?' + parsed.query if parsed.query else '')
    if path == request.get_full_path():
        return None
    return path


def return_url(request, fallback=None):
    return safe_return(request, request.POST.get('next') or request.GET.get('next')) or fallback or reverse('products')


def detail_url(request, name, pk):
    target = reverse(name, args=[pk])
    origin = safe_return(request, request.POST.get('next') or request.GET.get('next'))
    return target + ('?' + urlencode({'next': origin}) if origin else '')


def navigation(request):
    fallback = reverse('products') if request.path.startswith('/estoque/') else reverse('home')
    back = safe_return(request, request.POST.get('next') or request.GET.get('next'))
    back = back or safe_return(request, request.META.get('HTTP_REFERER')) or fallback
    return {'back_url': back, 'inventory_return_url': return_url(request), 'show_back': request.path not in (reverse('home'), reverse('dashboard')),
            'mvet_version':VERSION, 'can_manage_settings':can_manage_settings(request.user)}
