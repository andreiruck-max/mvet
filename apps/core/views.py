from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from .forms import CompanyForm
from .selectors import get_company
from .services import update_company

@login_required
@require_GET
def home(request):
    return render(request, "core/home.html", {"company": get_company()})

@login_required
@permission_required("core.manage_configuration", raise_exception=True)
@require_http_methods(["GET", "POST"])
def configuration(request):
    company = get_company()
    if company is None:
        return render(request, "core/setup_required.html", status=503)
    form = CompanyForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        try:
            update_company(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Configurações salvas.")
            return redirect("configuration")
    return render(request, "core/configuration.html", {"form": form, "company": company})

@login_required
@permission_required("core.view_dashboard", raise_exception=True)
@require_GET
def dashboard(request):
    return render(request, "core/not_available.html", {"title": "Indicadores", "description":
        "Os indicadores serão liberados após a validação dos módulos de vendas, estoque e despesas."})

@login_required
@permission_required("core.view_dre", raise_exception=True)
@require_GET
def dre(request):
    return render(request, "core/not_available.html", {"title": "DRE gerencial", "description":
        "A DRE por competência será liberada após a implementação e validação das fontes de receita, CMV e despesas."})

@login_required
@permission_required("core.view_finance", raise_exception=True)
@require_GET
def finance(request):
    return render(request, "core/not_available.html", {"title": "Financeiro", "description":
        "Contas, títulos, pagamentos e fluxo diário estão na próxima etapa de implementação."})

@login_required
@permission_required("core.view_dashboard", raise_exception=True)
@require_GET
def dashboard_api(request):
    return JsonResponse({"status": "not_implemented", "detail":
        "Indicadores ainda não implementados. Nenhum valor financeiro é retornado."}, status=501)
