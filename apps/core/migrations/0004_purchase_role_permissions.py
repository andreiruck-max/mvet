from django.db import migrations

def install(apps,schema_editor):
    ContentType=apps.get_model('contenttypes','ContentType');Permission=apps.get_model('auth','Permission');Group=apps.get_model('auth','Group')
    content_type,_=ContentType.objects.get_or_create(app_label='core',model='company')
    codes={'operate_purchases':'Cadastrar e receber compras','view_purchase_reports':'Visualizar relatórios consolidados de compras'}
    permissions={code:Permission.objects.get_or_create(content_type=content_type,codename=code,defaults={'name':name})[0] for code,name in codes.items()}
    for name,codenames in {'ADMINISTRADOR':list(codes),'FINANCEIRO':list(codes),'GERENCIAL':['view_purchase_reports']}.items():
        group=Group.objects.filter(name=name).first()
        if group:group.permissions.add(*(permissions[code] for code in codenames))

def uninstall(apps,schema_editor):
    Permission=apps.get_model('auth','Permission');Group=apps.get_model('auth','Group')
    permissions=Permission.objects.filter(content_type__app_label='core',codename__in=['operate_purchases','view_purchase_reports'])
    for group in Group.objects.filter(name__in=['ADMINISTRADOR','FINANCEIRO','GERENCIAL']):group.permissions.remove(*permissions)

class Migration(migrations.Migration):
    dependencies=[('core','0003_alter_company_options')]
    operations=[migrations.RunPython(install,uninstall)]
