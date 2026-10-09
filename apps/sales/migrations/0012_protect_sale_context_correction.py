from importlib import import_module
from django.db import migrations

previous = import_module('apps.sales.migrations.0011_protect_sale_corrections')


def function():
    fields = (*previous.FIELDS, 'tax_snapshot', 'revision', 'channel_id', 'location_id', 'stock_operation_id')
    allowed = ','.join("'"+field+"'" for field in fields)
    matches = ' AND '.join(f"(r.before->>'{field}')::numeric=OLD.{field} AND (r.after->>'{field}')::numeric=NEW.{field}"
                           for field in (*previous.FIELDS, 'channel_id', 'location_id', 'stock_operation_id'))
    branch = f"""
    IF NEW.status='CONFIRMED' AND NEW.revision=OLD.revision+1
      AND (to_jsonb(NEW)-ARRAY[{allowed}])=(to_jsonb(OLD)-ARRAY[{allowed}])
      AND EXISTS(SELECT 1 FROM sales_salecorrection r WHERE r.sale_id=OLD.id
        AND r.key::text=current_setting('mvet.sale_correction',true)
        AND r.before_revision=OLD.revision AND {matches}
        AND r.before->'tax_snapshot'=OLD.tax_snapshot AND r.after->'tax_snapshot'=NEW.tax_snapshot
        AND (
          (OLD.location_id=NEW.location_id AND OLD.stock_operation_id=NEW.stock_operation_id)
          OR (OLD.location_id<>NEW.location_id AND EXISTS (
            SELECT 1 FROM inventory_stockoperation outgoing
            JOIN inventory_stockoperation returned ON returned.id=outgoing.reversal_of_id
            WHERE outgoing.id=NEW.stock_operation_id AND outgoing.kind='SALE_OUT'
              AND returned.reversal_of_id=OLD.stock_operation_id AND returned.kind='SALE_RETURN'
              AND outgoing.actor_id=r.actor_id AND returned.actor_id=r.actor_id
              AND EXISTS(SELECT 1 FROM inventory_stockmovement WHERE operation_id=outgoing.id)
              AND NOT EXISTS(SELECT 1 FROM inventory_stockmovement WHERE operation_id=outgoing.id
                             AND (location_id<>NEW.location_id OR quantity>=0))
              AND NOT EXISTS(SELECT 1 FROM inventory_stockmovement WHERE operation_id=returned.id
                             AND (location_id<>OLD.location_id OR quantity<=0))
              AND NOT EXISTS(
                SELECT product_id FROM inventory_stockmovement
                WHERE operation_id IN (OLD.stock_operation_id, returned.id)
                GROUP BY product_id HAVING sum(quantity)<>0 OR sum(value+cost_variance)<>0)
              AND NOT EXISTS(
                SELECT product_id FROM inventory_stockmovement
                WHERE operation_id IN (outgoing.id, returned.id)
                GROUP BY product_id HAVING sum(quantity)<>0 OR sum(value+cost_variance)<>0)
          ))
        ))
    THEN RETURN NEW; END IF;
    """
    return previous.function().replace("IF OLD.status = 'CONFIRMED' THEN", "IF OLD.status = 'CONFIRMED' THEN\n"+branch, 1)


def install(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql': schema_editor.execute(function())


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql': schema_editor.execute(previous.function())


class Migration(migrations.Migration):
    dependencies = [('sales', '0011_protect_sale_corrections')]
    operations = [migrations.RunPython(install, uninstall)]
