from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from apps.core import views
from apps.reporting import views as reports
from apps.reporting.exports import export
from apps.notifications import views as notifications
from apps.accounts.views import AuditedPasswordChangeView
from apps.accounts.access import users as user_access

from apps.inventory.views import lookup
from apps.sales.views import sale_result
from apps.purchases.views import supplier_summary
from apps.finance.views import cash_api
from apps.expenses.views import report_api as expense_report_api

urlpatterns = [
    path('integracoes/bling/', include('apps.integrations.urls')),
    path('relatorios/exportar/<str:kind>/<str:format>/', export, name='report_export'),
    path('usuarios/', user_access, name='user_access_list'),
    path('usuarios/<int:pk>/acessos/', user_access, name='user_access'),
    path('notificacoes/', include('apps.notifications.urls')),
    path('api/v1/notificacoes/', notifications.api, name='notifications_api'),
    path('despesas/',include('apps.expenses.urls')),
    path('api/v1/despesas/competencia/',expense_report_api,name='expense_report_api'),
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
    path("indicadores/", reports.dashboard, name="dashboard"),
    path("relatorios/vendas/", reports.sales_sheet, name="sales_sheet"),
    path("relatorios/compras-a-pagar/", reports.purchase_payables, name="purchase_payables"),
    path("dre/", reports.dre, name="dre"),
    path("api/v1/dre/", reports.dre_api, name="dre_api"),
    path("financeiro/", include("apps.finance.urls")),
    path("api/v1/financeiro/diario/", cash_api, name="cash_api"),
    path("api/v1/indicadores/", reports.dashboard_api, name="dashboard_api"),
    path("admin/", admin.site.urls),
]
