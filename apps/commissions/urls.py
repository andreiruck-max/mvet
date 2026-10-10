from django.urls import path
from . import views
urlpatterns=[
    path('',views.index,name='commissions'),
    path('conferencia/',views.index,{'review':True},name='commission_review'),
    path('apuracao/',views.monthly,name='commission_monthly'),
    path('pagamentos/',views.payments,name='commission_payments'),
    path('pagamentos/novo/',views.payment,name='commission_payment_new'),
    path('configuracoes/',views.settings,name='commission_settings'),
    path('configuracoes/<int:pk>/',views.settings,name='commission_payee_edit'),
    path('nova/',views.create,name='commission_new'),
    path('venda/<int:sale_id>/',views.create,name='commission_sale'),
    path('<int:pk>/',views.detail,name='commission_detail'),
    path('<int:pk>/parcelas/',views.schedule,name='commission_schedule'),
    path('acao/<str:kind>/<int:pk>/',views.action,name='commission_action'),
]
