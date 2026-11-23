from django.core.management.color import no_style
from django.db import migrations


def ensure_primary(apps, schema_editor):
    company = apps.get_model('core', 'Company')
    alias = schema_editor.connection.alias
    company.objects.using(alias).get_or_create(pk=1)
    for sql in schema_editor.connection.ops.sequence_reset_sql(no_style(), [company]):
        schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [('core', '0014_remove_company_single_company_company_active_and_more')]
    operations = [migrations.RunPython(ensure_primary, migrations.RunPython.noop)]
