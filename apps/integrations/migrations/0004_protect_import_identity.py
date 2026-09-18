from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql': return
    schema_editor.execute("""CREATE FUNCTION mvet_protect_bling_import() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Imported invoice references cannot be deleted'; END IF;
      IF NEW.connection_id <> OLD.connection_id OR NEW.external_id <> OLD.external_id OR
         (OLD.access_key <> '' AND NEW.access_key <> OLD.access_key) THEN
        RAISE EXCEPTION 'External invoice identity is immutable';
      END IF;
      IF OLD.sale_id IS NOT NULL AND
         (NEW.sale_id IS DISTINCT FROM OLD.sale_id OR NEW.status <> 'IMPORTED' OR
          NEW.approved_source IS DISTINCT FROM OLD.approved_source) THEN
        RAISE EXCEPTION 'Approved invoice linkage and snapshot are immutable';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    schema_editor.execute('CREATE TRIGGER protect_bling_import BEFORE UPDATE OR DELETE ON integrations_invoiceimport FOR EACH ROW EXECUTE FUNCTION mvet_protect_bling_import()')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql': return
    schema_editor.execute('DROP TRIGGER protect_bling_import ON integrations_invoiceimport')
    schema_editor.execute('DROP FUNCTION mvet_protect_bling_import()')


class Migration(migrations.Migration):
    dependencies = [('integrations', '0003_importrun_error_ids_and_more')]
    operations = [migrations.RunPython(install, uninstall)]
