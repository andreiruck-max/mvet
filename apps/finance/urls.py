from django.urls import path
from . import views

urlpatterns=[
    path('',views.cash,name='finance'),
    path('titulos/',views.title_list,name='financial_titles'),
    path('titulos/novo/',views.title_new,name='financial_title_new'),
    path('titulos/<int:pk>/',views.title_detail,name='financial_title'),
    path('titulos/<int:pk>/liquidar/',views.title_action,{'action':'settle'},name='financial_settle'),
    path('titulos/<int:pk>/previsao/',views.title_action,{'action':'schedule'},name='financial_schedule'),
    path('titulos/<int:pk>/cancelar/',views.title_action,{'action':'cancel'},name='financial_cancel'),
    path('contas/',views.account_list,name='financial_accounts'),
    path('contas/nova/',views.account_edit,name='financial_account_new'),
    path('contas/<int:pk>/editar/',views.account_edit,name='financial_account_edit'),
    path('contas/<int:pk>/excluir/',views.account_delete,name='financial_account_delete'),
    path('transferir/',views.transfer_new,name='financial_transfer'),
    path('operacoes/<int:pk>/',views.operation_detail,name='financial_operation'),
    path('operacoes/<int:pk>/estornar/',views.operation_action,{'action':'reverse'},name='financial_reverse'),
    path('operacoes/<int:pk>/realizar/',views.operation_action,{'action':'post'},name='financial_post'),
    path('contas/<int:pk>/dia/<str:date>/',views.day_detail,name='financial_day'),
]
