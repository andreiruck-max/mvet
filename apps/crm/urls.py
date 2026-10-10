from django.urls import path
from . import views

urlpatterns=[
    path('',views.queue,name='crm_queue'),
    path('contatos/',views.queue,{'all_contacts':True},name='crm_contacts'),
    path('novo/',views.edit,name='crm_new'),
    path('contatos/<int:pk>/',views.detail,name='crm_detail'),
    path('contatos/<int:pk>/editar/',views.edit,name='crm_edit'),
    path('contatos/<int:pk>/registrar/',views.interaction,name='crm_interaction'),
    path('contatos/<int:pk>/acao/<str:action>/',views.state,name='crm_state'),
    path('regras/',views.rules,name='crm_rules'),
    path('aprovacoes/',views.approvals,name='crm_approvals'),
    path('aprovacoes/<int:pk>/',views.approvals,name='crm_decide'),
    path('indicadores/',views.report,name='crm_report'),
    path('importar/',views.import_contacts,name='crm_import'),
    path('importar/<uuid:batch_id>/',views.import_contacts,name='crm_import_preview'),
]
