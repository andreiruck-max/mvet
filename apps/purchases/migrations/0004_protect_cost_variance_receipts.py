from django.db import migrations


FUNCTION = """CREATE OR REPLACE FUNCTION mvet_protect_purchase_item() RETURNS trigger AS $$
DECLARE parent_status text;
BEGIN
  IF TG_OP<>'INSERT' THEN
    SELECT status INTO parent_status FROM purchases_purchase WHERE id=OLD.purchase_id;
    IF parent_status<>'DRAFT' THEN
      IF TG_OP='UPDATE' AND parent_status='ORDERED' AND OLD.movement_id IS NULL AND NEW.movement_id IS NOT NULL
        AND (to_jsonb(NEW)-'movement_id')=(to_jsonb(OLD)-'movement_id')
        AND EXISTS (SELECT 1 FROM inventory_stockmovement m JOIN inventory_stockoperation o ON o.id=m.operation_id
          JOIN purchases_purchase p ON p.id=OLD.purchase_id WHERE m.id=NEW.movement_id AND o.kind='PUR_RECEIPT'
          AND m.product_id=OLD.product_id AND m.location_id=p.location_id AND m.quantity=OLD.quantity
          AND {value_expression}=OLD.allocated_total)
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
END; $$ LANGUAGE plpgsql"""


def install(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute(FUNCTION.format(value_expression='m.value+m.cost_variance'))


def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor=='postgresql':
        schema_editor.execute(FUNCTION.format(value_expression='m.value'))


class Migration(migrations.Migration):
    dependencies=[
        ('purchases','0003_purchase_acquisition_kind_purchaseitem_category_and_more'),
        ('inventory','0008_remove_stockbalance_stock_nonnegative_and_more'),
    ]
    operations=[migrations.RunPython(install,uninstall)]
