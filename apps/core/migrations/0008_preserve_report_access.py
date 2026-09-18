from django.db import migrations


def preserve(apps, schema_editor):
    ContentType=apps.get_model('contenttypes','ContentType')
    Permission=apps.get_model('auth','Permission')
    Group=apps.get_model('auth','Group')
    User=apps.get_model('auth','User')
    ct,_=ContentType.objects.get_or_create(app_label='core',model='company')
    new,_=Permission.objects.get_or_create(content_type=ct,codename='view_sales_report',defaults={'name':'Consultar relatório detalhado de vendas'})
    for group in Group.objects.filter(permissions__content_type=ct,permissions__codename='view_dashboard'):
        group.permissions.add(new)
    for user in User.objects.filter(user_permissions__content_type=ct,user_permissions__codename='view_dashboard'):
        user.user_permissions.add(new)
    margin,_=Permission.objects.get_or_create(content_type=ct,codename='view_margins',defaults={'name':'Consultar margens de vendas'})
    for group in Group.objects.filter(permissions__content_type=ct,permissions__codename='view_costs'):
        group.permissions.add(margin)
    for user in User.objects.filter(user_permissions__content_type=ct,user_permissions__codename='view_costs'):
        user.user_permissions.add(margin)


class Migration(migrations.Migration):
    dependencies=[('core','0007_alter_company_options')]
    operations=[migrations.RunPython(preserve,migrations.RunPython.noop)]
