from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, Http404
from django.views.decorators.http import require_GET
from django.utils import timezone
from apps.core.models import Company
from apps.core.services import require, audit
from apps.inventory.services import domain_lock
from .datasets import build
from .files import xlsx, pdf


@login_required
@require_GET
def export(request, kind, format):
    category={'cash':'finance','titles':'finance','payables':'purchases'}.get(kind,kind)
    if category not in ['sales','stock','purchases','finance','expenses','dre','dashboard'] or format not in ['xlsx','pdf']:raise Http404
    require(request.user,'core.export_'+category)
    try:
        # Materialize a consistent projection, then release the write mutex.
        # Rendering large files must not block sales and payments.
        with transaction.atomic():
            domain_lock()
            dataset=build(kind,request.user,request.GET)
            company=Company.objects.get(pk=1)
        if format=='pdf' and len(dataset.rows)>2000:
            raise ValidationError('PDF limitado a 2.000 registros. Reduza os filtros ou exporte Excel; nenhum registro foi omitido.')
    except ValidationError as error:return HttpResponseBadRequest('; '.join(error.messages))
    content=xlsx(dataset,company.name) if format=='xlsx' else pdf(dataset,company.name)
    audit(request.user,company,'export_report',after={'report':kind,'format':format,'rows':len(dataset.rows),'filters':dict(request.GET.lists())})
    response=HttpResponse(content,content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if format=='xlsx' else 'application/pdf')
    response['Content-Disposition']=f'attachment; filename="mvet-{kind}-{timezone.localdate().isoformat()}.{format}"'
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
    return response
