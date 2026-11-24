from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        CREATE FUNCTION mvet_check_stock_owner() RETURNS trigger AS $$
        BEGIN
            IF TG_TABLE_NAME = 'inventory_stockmovement' THEN
                IF NOT EXISTS (SELECT 1 FROM inventory_stockoperation
                           WHERE id = NEW.operation_id AND company_id = NEW.company_id) THEN
                    RAISE EXCEPTION 'Stock movement owner differs from operation';
                END IF;
            ELSE
                IF NEW.reversal_of_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM inventory_stockoperation
                    WHERE id = NEW.reversal_of_id AND company_id = NEW.company_id
                ) THEN
                    RAISE EXCEPTION 'Stock reversal owner differs from source';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER stock_owner_integrity BEFORE INSERT ON inventory_stockmovement
            FOR EACH ROW EXECUTE FUNCTION mvet_check_stock_owner();
        CREATE TRIGGER stock_owner_integrity BEFORE INSERT ON inventory_stockoperation
            FOR EACH ROW EXECUTE FUNCTION mvet_check_stock_owner();
    """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        DROP TRIGGER stock_owner_integrity ON inventory_stockmovement;
        DROP TRIGGER stock_owner_integrity ON inventory_stockoperation;
        DROP FUNCTION mvet_check_stock_owner();
    """)


class Migration(migrations.Migration):
    dependencies = [('inventory', '0014_owner_balance_key')]
    operations = [migrations.RunPython(install, uninstall)]
