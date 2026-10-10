from django.db import migrations

TABLES=('commissions_command','commissions_entry','commissions_payment','commissions_allocation')

def protect(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute("""CREATE FUNCTION mvet_commission_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Commission ledger is immutable; record a reversal'; END; $$;""")
    for table in TABLES:
        schema_editor.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION mvet_commission_immutable();')

def unprotect(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    for table in TABLES:schema_editor.execute(f'DROP TRIGGER IF EXISTS {table}_immutable ON {table};')
    schema_editor.execute('DROP FUNCTION IF EXISTS mvet_commission_immutable();')

class Migration(migrations.Migration):
    dependencies=[('commissions','0002_entry_terms')]
    operations=[migrations.RunPython(protect,unprotect)]
