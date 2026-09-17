from django.db import migrations


def install(apps,schema_editor):
    ContentType=apps.get_model('contenttypes','ContentType');Permission=apps.get_model('auth','Permission');Group=apps.get_model('auth','Group')
    ct,_=ContentType.objects.get_or_create(app_label='core',model='company')
    codes={'operate_expenses':'Registrar e classificar despesas','manage_expense_rules':'Gerenciar plano de contas e regras','view_expense_reports':'Visualizar despesas consolidadas por competência'}
    permissions={code:Permission.objects.get_or_create(content_type=ct,codename=code,defaults={'name':name})[0] for code,name in codes.items()}
    for name,codenames in {'ADMINISTRADOR':list(codes),'FINANCEIRO':list(codes),'GERENCIAL':['view_expense_reports']}.items():
        group=Group.objects.filter(name=name).first()
        if group:group.permissions.add(*(permissions[c] for c in codenames))


class Migration(migrations.Migration):
    dependencies=[('core','0005_alter_company_options')]
    operations=[migrations.RunPython(install,migrations.RunPython.noop)]
