from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from apps.core.services import require
from . import services
from .forms import ConfigurationForm, PreferencesForm, ReadForm
from .models import AlertConfiguration, NotificationPreference, KINDS, BackupEvidence
from .selectors import visible, allowed_kinds, destination


def listing(request):
    query = visible(request.user)
    state = request.GET.get('state', 'active')
    if state != 'all':
        query = query.filter(active=state != 'resolved')
    if request.GET.get('read') in ('yes', 'no'):
        query = query.filter(is_read=request.GET['read'] == 'yes')
    if request.GET.get('kind'):
        query = query.filter(kind=request.GET['kind'])
    if request.GET.get('severity'):
        query = query.filter(severity=request.GET['severity'])
    page = Paginator(query, 30).get_page(request.GET.get('page'))
    for obj in page:
        obj.destination = destination(obj)
    return page


@login_required
@require_GET
def index(request):
    params = request.GET.copy()
    params.pop('page', None)
    config = AlertConfiguration.objects.filter(pk=1).first()
    return render(request, 'notifications/index.html', {
        'page': listing(request), 'query': params.urlencode(), 'config': config,
        'kinds': [(k, label) for k, label in KINDS if k in allowed_kinds(request.user)],
    })


@login_required
@require_GET
def api(request):
    page = listing(request)
    return JsonResponse({'count': page.paginator.count, 'page': page.number,
        'pages': page.paginator.num_pages, 'results': [dict(id=n.pk, title=n.title,
            description=n.description, severity=n.severity, kind=n.kind, active=n.active,
            read=n.is_read, revision=n.revision, updated_at=n.updated_at.isoformat(),
            url=n.destination) for n in page]})


@login_required
@require_POST
def read(request, pk):
    form = ReadForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest('Revisão inválida.')
    services.mark_read(actor=request.user, pk=pk, revision=form.cleaned_data['revision'])
    return redirect('notifications')


@login_required
@require_http_methods(['GET', 'POST'])
def preferences(request):
    disabled = NotificationPreference.objects.filter(user=request.user, enabled=False).values_list('kind', flat=True)
    form = PreferencesForm(request.POST if request.method == 'POST' else None, user=request.user,
        initial={'enabled': [k for k in allowed_kinds(request.user) if k not in disabled]})
    if request.method == 'POST' and form.is_valid():
        services.preferences(actor=request.user, enabled=form.cleaned_data['enabled'])
        messages.success(request, 'Preferências salvas.')
        return redirect('notifications')
    return render(request, 'notifications/form.html', {'form': form, 'title': 'Minhas preferências de alertas'})


@login_required
@require_http_methods(['GET', 'POST'])
def configuration(request):
    require(request.user, 'core.manage_alerts')
    config = AlertConfiguration.objects.filter(pk=1).first() or AlertConfiguration(pk=1)
    form = ConfigurationForm(request.POST if request.method == 'POST' else None, instance=config)
    if request.method == 'POST' and form.is_valid():
        try:
            services.configure(actor=request.user, data=form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Configuração salva. O próximo processamento aplicará as regras.')
            return redirect('notification_configuration')
    return render(request, 'notifications/form.html', {'form': form, 'title': 'Configuração dos alertas',
        'configuration': True, 'evidence': BackupEvidence.objects.all()[:10]})


@login_required
@require_POST
def refresh(request):
    require(request.user, 'core.manage_alerts')
    services.refresh()
    messages.success(request, 'Alertas atualizados.')
    return redirect('notifications')
