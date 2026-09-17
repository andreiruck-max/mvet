from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='notifications'),
    path('preferencias/', views.preferences, name='notification_preferences'),
    path('configuracao/', views.configuration, name='notification_configuration'),
    path('atualizar/', views.refresh, name='notification_refresh'),
    path('<int:pk>/ler/', views.read, name='notification_read'),
]
