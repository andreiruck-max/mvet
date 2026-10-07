from importlib import import_module
from django.db import migrations

previous=import_module('apps.sales.migrations.0005_audited_tax_recalculation')
RECOVERY="""
IF OLD.status='CANCELLED' AND NEW.status='CONFIRMED'
 AND NEW.return_operation_id IS NULL AND NEW.cancelled_by_id IS NULL
 AND NEW.cancelled_at IS NULL AND NEW.cancellation_reason=''
 AND NEW.revision=OLD.revision+1
 AND (to_jsonb(NEW) - ARRAY['status','fees','stock_operation_id','return_operation_id','cancelled_by_id','cancelled_at','cancellation_reason','revision'])
     = (to_jsonb(OLD) - ARRAY['status','fees','stock_operation_id','return_operation_id','cancelled_by_id','cancelled_at','cancellation_reason','revision'])
 AND EXISTS (SELECT 1 FROM sales_salerecovery r
   JOIN inventory_stockoperation o ON o.id=r.recovery_operation_id
   WHERE r.sale_id=OLD.id AND r.key::text=current_setting('mvet.sale_recovery',true)
     AND r.before_revision=OLD.revision AND r.before_fees=OLD.fees AND r.after_fees=NEW.fees
     AND r.original_operation_id=OLD.stock_operation_id AND r.returned_operation_id=OLD.return_operation_id
     AND r.recovery_operation_id=NEW.stock_operation_id
     AND o.reversal_of_id=OLD.return_operation_id AND o.kind='SALE_OUT' AND o.actor_id=r.actor_id)
THEN RETURN NEW; END IF;
"""

def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    sql=previous.BASE_FUNCTION.format(tax_branch=previous.TAX_BRANCH)
    sql=sql.replace("IF OLD.status = 'CANCELLED'",RECOVERY+"\nIF OLD.status = 'CANCELLED'",1)
    schema_editor.execute(sql)
    schema_editor.execute('CREATE TRIGGER immutable_sale_recovery BEFORE UPDATE OR DELETE ON sales_salerecovery FOR EACH ROW EXECUTE FUNCTION mvet_reject_ledger_change()')

def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute('DROP TRIGGER immutable_sale_recovery ON sales_salerecovery')
    schema_editor.execute(previous.BASE_FUNCTION.format(tax_branch=previous.TAX_BRANCH))

class Migration(migrations.Migration):
    dependencies=[('sales','0008_salerecovery')]
    operations=[migrations.RunPython(install,uninstall)]
