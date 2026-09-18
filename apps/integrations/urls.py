from django.urls import path
from . import views

urlpatterns = [
    path('', views.queue, name='bling_queue'),
    path('consultar/', views.query, name='bling_query'),
    path('conexao/', views.connection, name='bling_connection'),
    path('conectar/', views.connect, name='bling_connect'),
    path('retorno/', views.callback, name='bling_callback'),
    path('desconectar/', views.disconnect, name='bling_disconnect'),
    path('<int:pk>/', views.detail, name='bling_detail'),
    path('<int:pk>/produto/', views.alias, name='bling_alias'),
    path('<int:pk>/<str:action>/', views.decision, name='bling_decision'),
]
