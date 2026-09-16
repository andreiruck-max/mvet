from django.db import migrations

BASE_FUNCTION="""CREATE OR REPLACE FUNCTION mvet_protect_sale() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Sales must be cancelled, never deleted'; END IF;
  IF OLD.status = 'CANCELLED' THEN RAISE EXCEPTION 'Cancelled sale is immutable'; END IF;
  IF OLD.status = 'CONFIRMED' THEN
    {tax_branch}
    IF NEW.status <> 'CANCELLED' OR
      (to_jsonb(NEW) - ARRAY['status','cancelled_by_id','cancelled_at','cancellation_reason','return_operation_id','revision']) IS DISTINCT FROM
      (to_jsonb(OLD) - ARRAY['status','cancelled_by_id','cancelled_at','cancellation_reason','return_operation_id','revision'])
    THEN RAISE EXCEPTION 'Confirmed sale snapshots are immutable'; END IF;
  END IF;
  RETURN NEW;
END; $$ LANGUAGE plpgsql"""

TAX_BRANCH="""
IF (to_jsonb(NEW) - ARRAY['tax_amount','tax_snapshot']) = (to_jsonb(OLD) - ARRAY['tax_amount','tax_snapshot'])
  AND EXISTS (SELECT 1 FROM sales_saletaxrevision r WHERE r.sale_id=OLD.id
    AND r.change_id::text=current_setting('mvet.tax_revision',true)
    AND r.before_amount=OLD.tax_amount AND r.after_amount=NEW.tax_amount
    AND r.before_snapshot=OLD.tax_snapshot AND r.after_snapshot=NEW.tax_snapshot)
THEN RETURN NEW; END IF;
"""

def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute(BASE_FUNCTION.format(tax_branch=TAX_BRANCH))
    for table in ('sales_taxratechange','sales_saletaxrevision'):
        schema_editor.execute(f'CREATE TRIGGER immutable_tax_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION mvet_reject_ledger_change()')
    schema_editor.execute('CREATE TRIGGER protect_sale_extra BEFORE INSERT OR UPDATE OR DELETE ON sales_saleextracost FOR EACH ROW EXECUTE FUNCTION mvet_protect_sale_item()')

def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute(BASE_FUNCTION.format(tax_branch=''))
    for table in ('sales_taxratechange','sales_saletaxrevision'):
        schema_editor.execute(f'DROP TRIGGER immutable_tax_history ON {table}')
    schema_editor.execute('DROP TRIGGER protect_sale_extra ON sales_saleextracost')

class Migration(migrations.Migration):
    dependencies=[('sales','0004_sale_extra_costs_total_taxratechange_saletaxrevision_and_more')]
    operations=[migrations.RunPython(install,uninstall)]
