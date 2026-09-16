from django.urls import path
from . import views
urlpatterns=[
    path('',views.purchase_list,name='purchases'),path('nova/',views.purchase_edit,name='purchase_new'),
    path('<int:pk>/',views.purchase_detail,name='purchase_detail'),path('<int:pk>/editar/',views.purchase_edit,name='purchase_edit'),
    path('<int:pk>/confirmar/',views.purchase_confirm,name='purchase_confirm'),path('<int:pk>/receber/',views.purchase_receive,name='purchase_receive'),path('<int:pk>/cancelar/',views.purchase_cancel,name='purchase_cancel'),
    path('fornecedores/',views.supplier_list,name='suppliers'),path('fornecedores/novo/',views.supplier_edit,name='supplier_new'),path('fornecedores/<int:pk>/',views.supplier_detail,name='supplier_detail'),path('fornecedores/<int:pk>/editar/',views.supplier_edit,name='supplier_edit'),
]
