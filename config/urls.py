from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from apps.core import views
from apps.accounts.views import AuditedPasswordChangeView

from apps.inventory.views import lookup
from apps.sales.views import sale_result
from apps.purchases.views import supplier_summary
from apps.finance.views import cash_api

urlpatterns = [
    path("compras/", include("apps.purchases.urls")),
    path("api/v1/fornecedores/<int:pk>/resumo/", supplier_summary, name="supplier_summary"),
    path("vendas/", include("apps.sales.urls")),
    path("api/v1/vendas/<int:pk>/resultado/", sale_result, name="sale_result"),
    path("estoque/", include("apps.inventory.urls")),
    path("api/v1/produtos/", lookup, name="product_lookup"),
    path("entrar/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path("senha/", AuditedPasswordChangeView.as_view(), name="password_change"),
    path("", views.home, name="home"),
    path("configuracoes/", views.configuration, name="configuration"),
    path("indicadores/", views.dashboard, name="dashboard"),
    path("dre/", views.dre, name="dre"),
    path("financeiro/", include("apps.finance.urls")),
    path("api/v1/financeiro/diario/", cash_api, name="cash_api"),
    path("api/v1/indicadores/", views.dashboard_api, name="dashboard_api"),
    path("admin/", admin.site.urls),
]
