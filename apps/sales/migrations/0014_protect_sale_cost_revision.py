from importlib import import_module
from django.db import migrations

previous = import_module('apps.sales.migrations.0012_protect_sale_context_correction')
BRANCH = """
    IF NEW.status='CONFIRMED' AND NEW.revision=OLD.revision+1
      AND (to_jsonb(NEW)-ARRAY['cmv_adjustment','revision'])=(to_jsonb(OLD)-ARRAY['cmv_adjustment','revision'])
      AND NEW.cmv+NEW.cmv_adjustment>=0
      AND EXISTS(SELECT 1 FROM sales_salecostrevision r WHERE r.sale_id=OLD.id
        AND r.key::text=current_setting('mvet.sale_cost_revision',true)
        AND r.before_revision=OLD.revision
        AND r.before_adjustment=OLD.cmv_adjustment AND r.after_adjustment=NEW.cmv_adjustment
        AND (r.before->>'total')::numeric=OLD.cmv+OLD.cmv_adjustment
        AND (r.after->>'total')::numeric=NEW.cmv+NEW.cmv_adjustment)
    THEN RETURN NEW; END IF;
"""


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql': return
    schema_editor.execute(previous.function().replace("IF OLD.status = 'CONFIRMED' THEN", "IF OLD.status = 'CONFIRMED' THEN\n" + BRANCH, 1))
    schema_editor.execute('CREATE TRIGGER immutable_sale_cost_revision BEFORE UPDATE OR DELETE ON sales_salecostrevision FOR EACH ROW EXECUTE FUNCTION mvet_reject_ledger_change()')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql': return
    schema_editor.execute('DROP TRIGGER immutable_sale_cost_revision ON sales_salecostrevision')
    schema_editor.execute(previous.function())


class Migration(migrations.Migration):
    dependencies = [('sales', '0013_sale_cmv_adjustment_salecostrevision')]
    operations = [migrations.RunPython(install, uninstall)]
