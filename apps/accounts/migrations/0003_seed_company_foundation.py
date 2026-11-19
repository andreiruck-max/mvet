from django.conf import settings
from django.core.management.color import no_style
from django.db import migrations


def seed_foundation(apps, schema_editor):
    alias = schema_editor.connection.alias
    Company = apps.get_model('core', 'Company')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Grant = apps.get_model('accounts', 'UserCompanyAccess')
    Company.objects.using(alias).get_or_create(pk=2, defaults={
        'name': 'MVET PRODUTOS AGROVETERINÁRIOS LTDA',
        'trade_name': 'MVET AGRO COMERCIAL', 'active': False})
    if Company.objects.using(alias).filter(pk=1).exists():
        # Do not copy or reinterpret global permissions. Preserve the live legacy policy.
        for user_id in User.objects.using(alias).values_list('pk', flat=True).iterator():
            Grant.objects.using(alias).get_or_create(user_id=user_id, company_id=1,
                defaults={'inherit_legacy': True, 'active': True})
    for sql in schema_editor.connection.ops.sequence_reset_sql(no_style(), [Company]):
        schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0002_usercompanyaccess'),
        ('core', '0014_remove_company_single_company_company_active_and_more'),
    ]
    # Reversal would discard registrations/access history. Restore a lab checkpoint instead.
    operations = [migrations.RunPython(seed_foundation)]
