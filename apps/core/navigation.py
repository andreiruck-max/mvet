from urllib.parse import urlsplit, urlencode
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


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
    return {'back_url': back, 'inventory_return_url': return_url(request), 'show_back': request.path != reverse('home')}
