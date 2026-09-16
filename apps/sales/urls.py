from django.urls import path
from . import views
urlpatterns=[
    path('',views.sale_list,name='sales'),
    path('nova/',views.sale_edit,name='sale_new'),
    path('<int:pk>/',views.sale_detail,name='sale_detail'),
    path('<int:pk>/editar/',views.sale_edit,name='sale_edit'),
    path('<int:pk>/confirmar/',views.sale_confirm,name='sale_confirm'),
    path('<int:pk>/cancelar/',views.sale_cancel,name='sale_cancel'),
    path('configuracoes/<str:kind>/',views.configuration,name='sales_configuration'),
    path('configuracoes/<str:kind>/<int:pk>/',views.configuration,name='sales_configuration_edit'),
]
