from django.db import migrations

def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute("""CREATE FUNCTION mvet_protect_purchase() RETURNS trigger AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Purchases must be cancelled'; END IF;
      IF OLD.status='CANCELLED' THEN RAISE EXCEPTION 'Cancelled purchase is immutable'; END IF;
      IF OLD.status='ORDERED' THEN
        IF NEW.status NOT IN ('RECEIVED','CANCELLED') OR
          (to_jsonb(NEW)-ARRAY['status','received_date','receipt_id','received_by_id','received_at','cancelled_by_id','cancelled_at','cancellation_reason','revision']) IS DISTINCT FROM
          (to_jsonb(OLD)-ARRAY['status','received_date','receipt_id','received_by_id','received_at','cancelled_by_id','cancelled_at','cancellation_reason','revision'])
        THEN RAISE EXCEPTION 'Confirmed purchase is immutable'; END IF;
      END IF;
      IF OLD.status='RECEIVED' THEN
        IF NEW.status<>'CANCELLED' OR
          (to_jsonb(NEW)-ARRAY['status','reversal_id','cancelled_by_id','cancelled_at','cancellation_reason','revision']) IS DISTINCT FROM
          (to_jsonb(OLD)-ARRAY['status','reversal_id','cancelled_by_id','cancelled_at','cancellation_reason','revision'])
        THEN RAISE EXCEPTION 'Received purchase is immutable'; END IF;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""")
    schema_editor.execute('CREATE TRIGGER protect_purchase BEFORE UPDATE OR DELETE ON purchases_purchase FOR EACH ROW EXECUTE FUNCTION mvet_protect_purchase()')
    schema_editor.execute("""CREATE FUNCTION mvet_protect_purchase_item() RETURNS trigger AS $$
    DECLARE parent_status text;
    BEGIN
      IF TG_OP<>'INSERT' THEN
        SELECT status INTO parent_status FROM purchases_purchase WHERE id=OLD.purchase_id;
        IF parent_status<>'DRAFT' THEN
          IF TG_OP='UPDATE' AND parent_status='ORDERED' AND OLD.movement_id IS NULL AND NEW.movement_id IS NOT NULL
            AND (to_jsonb(NEW)-'movement_id')=(to_jsonb(OLD)-'movement_id')
            AND EXISTS (SELECT 1 FROM inventory_stockmovement m JOIN inventory_stockoperation o ON o.id=m.operation_id
              JOIN purchases_purchase p ON p.id=OLD.purchase_id WHERE m.id=NEW.movement_id AND o.kind='PUR_RECEIPT'
              AND m.product_id=OLD.product_id AND m.location_id=p.location_id AND m.quantity=OLD.quantity AND m.value=OLD.allocated_total)
          THEN RETURN NEW; END IF;
          RAISE EXCEPTION 'Historic purchase item is immutable';
        END IF;
      END IF;
      IF TG_OP<>'DELETE' THEN
        SELECT status INTO parent_status FROM purchases_purchase WHERE id=NEW.purchase_id;
        IF parent_status<>'DRAFT' THEN RAISE EXCEPTION 'Cannot add items to confirmed purchase'; END IF;
        RETURN NEW;
      END IF;
      RETURN OLD;
    END; $$ LANGUAGE plpgsql""")
    schema_editor.execute('CREATE TRIGGER protect_purchase_item BEFORE INSERT OR UPDATE OR DELETE ON purchases_purchaseitem FOR EACH ROW EXECUTE FUNCTION mvet_protect_purchase_item()')
    schema_editor.execute("""CREATE FUNCTION mvet_protect_purchase_installment() RETURNS trigger AS $$
    DECLARE parent_status text;
    BEGIN
      IF TG_OP<>'INSERT' THEN
        SELECT status INTO parent_status FROM purchases_purchase WHERE id=OLD.purchase_id;
        IF parent_status<>'DRAFT' THEN
          IF TG_OP='UPDATE' AND parent_status IN ('ORDERED','RECEIVED') AND OLD.status='PENDING' AND NEW.status='CANCELLED'
            AND (to_jsonb(NEW)-'status')=(to_jsonb(OLD)-'status') THEN RETURN NEW; END IF;
          RAISE EXCEPTION 'Historic purchase installment is immutable';
        END IF;
      END IF;
      IF TG_OP<>'DELETE' THEN
        SELECT status INTO parent_status FROM purchases_purchase WHERE id=NEW.purchase_id;
        IF parent_status<>'DRAFT' THEN RAISE EXCEPTION 'Cannot add installments to confirmed purchase'; END IF;
        RETURN NEW;
      END IF;
      RETURN OLD;
    END; $$ LANGUAGE plpgsql""")
    schema_editor.execute('CREATE TRIGGER protect_purchase_installment BEFORE INSERT OR UPDATE OR DELETE ON purchases_purchaseinstallment FOR EACH ROW EXECUTE FUNCTION mvet_protect_purchase_installment()')

def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    for suffix,table in [('purchase','purchases_purchase'),('purchase_item','purchases_purchaseitem'),('purchase_installment','purchases_purchaseinstallment')]:
        schema_editor.execute(f'DROP TRIGGER protect_{suffix} ON {table}')
        schema_editor.execute(f'DROP FUNCTION mvet_protect_{suffix}()')

class Migration(migrations.Migration):
    dependencies=[('purchases','0001_initial')]
    operations=[migrations.RunPython(install,uninstall)]
