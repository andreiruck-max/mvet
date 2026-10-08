from importlib import import_module
from django.db import migrations

base=import_module('apps.sales.migrations.0005_audited_tax_recalculation')
recovery=import_module('apps.sales.migrations.0009_protect_sale_recovery')
FIELDS=('products_amount','discount','shipping_received','shipping_paid','fees','difal','commission','other_costs','tax_amount')

def function():
    allowed=','.join("'"+field+"'" for field in (*FIELDS,'tax_snapshot','revision'))
    matches=' AND '.join(f"(r.before->>'{field}')::numeric=OLD.{field} AND (r.after->>'{field}')::numeric=NEW.{field}" for field in FIELDS)
    branch=f"""
    IF OLD.status='CONFIRMED' AND NEW.status='CONFIRMED' AND NEW.revision=OLD.revision+1
      AND (to_jsonb(NEW)-ARRAY[{allowed}])=(to_jsonb(OLD)-ARRAY[{allowed}])
      AND EXISTS(SELECT 1 FROM sales_salecorrection r WHERE r.sale_id=OLD.id
        AND r.key::text=current_setting('mvet.sale_correction',true)
        AND r.before_revision=OLD.revision AND {matches}
        AND r.before->'tax_snapshot'=OLD.tax_snapshot AND r.after->'tax_snapshot'=NEW.tax_snapshot)
    THEN RETURN NEW; END IF;
    """
    sql=base.BASE_FUNCTION.format(tax_branch=branch+base.TAX_BRANCH)
    return sql.replace("IF OLD.status = 'CANCELLED'",recovery.RECOVERY+"\nIF OLD.status = 'CANCELLED'",1)

def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute(function())
    schema_editor.execute('CREATE TRIGGER immutable_sale_correction BEFORE UPDATE OR DELETE ON sales_salecorrection FOR EACH ROW EXECUTE FUNCTION mvet_reject_ledger_change()')

def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute('DROP TRIGGER immutable_sale_correction ON sales_salecorrection')
    sql=base.BASE_FUNCTION.format(tax_branch=base.TAX_BRANCH)
    schema_editor.execute(sql.replace("IF OLD.status = 'CANCELLED'",recovery.RECOVERY+"\nIF OLD.status = 'CANCELLED'",1))

class Migration(migrations.Migration):
    dependencies=[('sales','0010_salecorrection')]
    operations=[migrations.RunPython(install,uninstall)]
