from django.urls import path
from . import views

urlpatterns=[
    path('',views.expense_list,name='expenses'),
    path('nova/',views.expense_new,name='expense_new'),
    path('relatorio/',views.report,name='expense_report'),
    path('configuracoes/',views.configuration_list,name='expense_configuration'),
    path('categorias/nova/',views.configuration_edit,{'kind':'category'},name='expense_category_new'),
    path('categorias/<int:pk>/',views.configuration_edit,{'kind':'category'},name='expense_category_edit'),
    path('regras/nova/',views.configuration_edit,{'kind':'rule'},name='expense_rule_new'),
    path('regras/<int:pk>/',views.configuration_edit,{'kind':'rule'},name='expense_rule_edit'),
    path('<int:pk>/',views.expense_detail,name='expense_detail'),
    path('<int:pk>/classificar/',views.expense_action,{'action':'classify'},name='expense_classify'),
    path('<int:pk>/cancelar/',views.expense_action,{'action':'cancel'},name='expense_cancel'),
    path('<int:pk>/recorrencia/',views.recurrence,name='expense_recurrence'),
    path('<int:pk>/parar/',views.expense_action,{'action':'stop'},name='expense_stop'),
]
