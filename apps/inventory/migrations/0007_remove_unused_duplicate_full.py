from django.db import migrations


def clean_unused_full(apps, schema_editor):
    Location = apps.get_model('inventory', 'StockLocation')
    alias = schema_editor.connection.alias
    old = Location.objects.using(alias).filter(name='Estoque Full').first()
    if old is None:
        return
    canonical = Location.objects.using(alias).filter(name='Full Mercado Livre').first()
    if canonical is None:
        old.name = 'Full Mercado Livre'
        old.save(using=alias, update_fields=['name'])
        return
    # An empty monetary total alone does not prove a location is unused.
    # Preserve all referenced locations, including zero stock history and drafts.
    for relation in Location._meta.related_objects:
        if relation.related_model.objects.using(alias).filter(**{relation.field.name: old.pk}).exists():
            return
    old.delete(using=alias)


class Migration(migrations.Migration):
    dependencies = [('inventory', '0006_stockbalance_average_cost_stockbalance_value_and_more'),
                    ('sales', '0001_initial'), ('purchases', '0001_initial'),
                    ('core', '0002_company_default_stock_location')]
    operations = [migrations.RunPython(clean_unused_full, migrations.RunPython.noop)]
