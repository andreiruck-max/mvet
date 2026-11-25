from django.db import migrations
from django.db.models import F, Q


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        CREATE FUNCTION mvet_check_sale_owner_links() RETURNS trigger AS $$
        BEGIN
            IF NEW.channel_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM sales_saleschannel WHERE id=NEW.channel_id AND company_id=NEW.company_id
            ) THEN RAISE EXCEPTION 'Sale channel belongs to another company' USING ERRCODE = '23503'; END IF;
            IF NEW.tax_rule_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM sales_taxrule WHERE id=NEW.tax_rule_id AND company_id=NEW.company_id
            ) THEN RAISE EXCEPTION 'Sale tax rule belongs to another company' USING ERRCODE = '23503'; END IF;
            IF NEW.commission_payee_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM commissions_payee WHERE id=NEW.commission_payee_id AND company_id=NEW.company_id
            ) THEN RAISE EXCEPTION 'Sale payee belongs to another company' USING ERRCODE = '23503'; END IF;
            IF NEW.stock_operation_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM inventory_stockoperation WHERE id=NEW.stock_operation_id AND company_id=NEW.company_id
            ) THEN RAISE EXCEPTION 'Sale stock operation belongs to another company' USING ERRCODE = '23503'; END IF;
            IF NEW.return_operation_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM inventory_stockoperation WHERE id=NEW.return_operation_id AND company_id=NEW.company_id
            ) THEN RAISE EXCEPTION 'Sale return operation belongs to another company' USING ERRCODE = '23503'; END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER sale_owner_links BEFORE INSERT OR UPDATE OF
            company_id,channel_id,tax_rule_id,commission_payee_id,stock_operation_id,return_operation_id
            ON sales_sale FOR EACH ROW EXECUTE FUNCTION mvet_check_sale_owner_links();

        CREATE FUNCTION mvet_check_consumption_owner() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM sales_saleitem
                WHERE id=NEW.item_id AND company_id=NEW.company_id)
                OR NOT EXISTS (SELECT 1 FROM inventory_stockmovement
                WHERE id=NEW.movement_id AND company_id=NEW.company_id) THEN
                RAISE EXCEPTION 'Sale consumption references another company' USING ERRCODE = '23503';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER consumption_owner_links BEFORE INSERT ON sales_saleconsumption
            FOR EACH ROW EXECUTE FUNCTION mvet_check_consumption_owner();
    """)
    # New triggers cover future writes. Refuse to certify an inconsistent existing
    # ledger; never repair historical documents while installing the guards.
    db = schema_editor.connection.alias
    for model, fields in [
        ('Sale', ('channel', 'tax_rule', 'commission_payee', 'stock_operation', 'return_operation')),
        ('SaleConsumption', ('item', 'movement')),
    ]:
        differences = Q()
        for field in fields:
            differences |= Q(**{f'{field}__isnull': False}) & ~Q(company_id=F(f'{field}__company_id'))
        if apps.get_model('sales', model).objects.using(db).filter(differences).exists():
            raise RuntimeError(f'{model}: vínculo empresarial inconsistente. Revise antes de migrar.')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute("""
        DROP TRIGGER consumption_owner_links ON sales_saleconsumption;
        DROP FUNCTION mvet_check_consumption_owner();
        DROP TRIGGER sale_owner_links ON sales_sale;
        DROP FUNCTION mvet_check_sale_owner_links();
    """)


class Migration(migrations.Migration):
    dependencies = [('sales', '0022_company_sales_channels'), ('inventory', '0015_owner_ledger_integrity')]
    operations = [migrations.RunPython(install, uninstall)]
