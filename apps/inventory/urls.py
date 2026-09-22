from django.urls import path
from . import views
urlpatterns=[
 path('produtos/<int:pk>/contar/<int:location_id>/', views.product_count, name='product_count'),
 path('produtos/<int:pk>/inativar/', views.product_inactivate, name='product_inactivate'),
 path('produtos/',views.products,name='products'),path('produtos/novo/',views.product_edit,name='product_new'),
 path('produtos/<int:pk>/',views.product_detail,name='product_detail'),path('produtos/<int:pk>/editar/',views.product_edit,name='product_edit'),
 path('produtos/<int:pk>/excluir/',views.product_remove,name='product_remove'),path('produtos/<int:pk>/componentes/',views.components,name='components'),
 path('movimentos/',views.operations,name='operations'),path('movimentos/novo/',views.operation_new,name='operation_new'),
 path('movimentos/<int:pk>/',views.operation_detail,name='operation_detail'),
 path('cadastros/<str:kind>/',views.named,name='named'),path('cadastros/<str:kind>/<int:pk>/',views.named,name='named_edit'),
]
