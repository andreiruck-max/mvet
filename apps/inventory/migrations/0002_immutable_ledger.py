from django.db import migrations

def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute("""CREATE FUNCTION mvet_reject_ledger_change() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'Immutable inventory ledger: use a reversal'; END;
    $$ LANGUAGE plpgsql;""")
    for table in ('inventory_stockoperation','inventory_stockmovement'):
        schema_editor.execute(f'CREATE TRIGGER immutable_ledger BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION mvet_reject_ledger_change()')

def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    for table in ('inventory_stockoperation','inventory_stockmovement'):
        schema_editor.execute(f'DROP TRIGGER immutable_ledger ON {table}')
    schema_editor.execute('DROP FUNCTION mvet_reject_ledger_change()')

class Migration(migrations.Migration):
    dependencies=[('inventory','0001_initial')]
    operations=[migrations.RunPython(install,uninstall)]
