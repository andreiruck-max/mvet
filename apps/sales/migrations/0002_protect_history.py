from django.db import migrations


def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute('CREATE TRIGGER immutable_consumption BEFORE UPDATE OR DELETE ON sales_saleconsumption FOR EACH ROW EXECUTE FUNCTION mvet_reject_ledger_change()')
    schema_editor.execute("""CREATE FUNCTION mvet_protect_sale() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Sales must be cancelled, never deleted'; END IF;
      IF OLD.status = 'CANCELLED' THEN RAISE EXCEPTION 'Cancelled sale is immutable'; END IF;
      IF OLD.status = 'CONFIRMED' THEN
        IF NEW.status <> 'CANCELLED' OR
          (to_jsonb(NEW) - ARRAY['status','cancelled_by_id','cancelled_at','cancellation_reason','return_operation_id','revision']) IS DISTINCT FROM
          (to_jsonb(OLD) - ARRAY['status','cancelled_by_id','cancelled_at','cancellation_reason','return_operation_id','revision'])
        THEN RAISE EXCEPTION 'Confirmed sale snapshots are immutable'; END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    schema_editor.execute('CREATE TRIGGER protect_sale BEFORE UPDATE OR DELETE ON sales_sale FOR EACH ROW EXECUTE FUNCTION mvet_protect_sale()')
    schema_editor.execute("""CREATE FUNCTION mvet_protect_sale_item() RETURNS trigger AS $$
    DECLARE sale_status text;
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        SELECT status INTO sale_status FROM sales_sale WHERE id=OLD.sale_id;
        IF sale_status <> 'DRAFT' THEN RAISE EXCEPTION 'Historic sale items are immutable'; END IF;
      END IF;
      IF TG_OP <> 'DELETE' THEN
        SELECT status INTO sale_status FROM sales_sale WHERE id=NEW.sale_id;
        IF sale_status <> 'DRAFT' THEN RAISE EXCEPTION 'Cannot change confirmed sale items'; END IF;
        RETURN NEW;
      END IF;
      RETURN OLD;
    END; $$ LANGUAGE plpgsql""")
    schema_editor.execute('CREATE TRIGGER protect_sale_item BEFORE INSERT OR UPDATE OR DELETE ON sales_saleitem FOR EACH ROW EXECUTE FUNCTION mvet_protect_sale_item()')


def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute('DROP TRIGGER protect_sale_item ON sales_saleitem')
    schema_editor.execute('DROP FUNCTION mvet_protect_sale_item()')
    schema_editor.execute('DROP TRIGGER protect_sale ON sales_sale')
    schema_editor.execute('DROP FUNCTION mvet_protect_sale()')
    schema_editor.execute('DROP TRIGGER immutable_consumption ON sales_saleconsumption')

class Migration(migrations.Migration):
    dependencies=[('sales','0001_initial'),('inventory','0002_immutable_ledger')]
    operations=[migrations.RunPython(install,uninstall)]
