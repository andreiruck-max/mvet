"""Keep the owner on both sides of each purchase link, including direct SQL."""
from django.db import migrations


# Names are explicit so reversal removes only the keys installed by this migration.
TARGETS = {
    'purchases_purchase': 'mvet3_purchase_owner_key',
    'purchases_purchaseinstallment': 'mvet3_installment_owner_key',
    'finance_financialaccount': 'mvet3_account_owner_key',
    'expenses_chartofaccount': 'mvet3_category_owner_key',
    'inventory_stockoperation': 'mvet3_stockop_owner_key',
    'inventory_stockmovement': 'mvet3_stockmove_owner_key',
}
LINKS = [
    ('purchases_purchase', 'account_id', 'finance_financialaccount', 'purchase_owner_account_fk'),
    ('purchases_purchase', 'receipt_id', 'inventory_stockoperation', 'purchase_owner_receipt_fk'),
    ('purchases_purchase', 'reversal_id', 'inventory_stockoperation', 'purchase_owner_reversal_fk'),
    ('purchases_purchaseitem', 'purchase_id', 'purchases_purchase', 'purchase_owner_item_fk'),
    ('purchases_purchaseitem', 'movement_id', 'inventory_stockmovement', 'purchase_owner_movement_fk'),
    ('purchases_purchaseitem', 'category_id', 'expenses_chartofaccount', 'purchase_owner_category_fk'),
    ('purchases_purchaseinstallment', 'purchase_id', 'purchases_purchase', 'purchase_owner_installment_fk'),
    ('finance_financialtitle', 'purchase_installment_id', 'purchases_purchaseinstallment', 'purchase_owner_title_fk'),
    ('finance_financialtitle', 'account_id', 'finance_financialaccount', 'finance_title_owner_account_fk'),
]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table, name in TARGETS.items():
        schema_editor.execute(f'ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE (company_id, id)')
    for table, field, target, name in LINKS:
        # PostgreSQL also checks existing rows. A mismatch aborts the atomic migration.
        # MATCH SIMPLE permits a genuinely absent optional FK and never skips a non-null one.
        schema_editor.execute(f'ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY (company_id, {field}) '
                              f'REFERENCES {target} (company_id, id) DEFERRABLE INITIALLY IMMEDIATE')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table, _, _, name in reversed(LINKS):
        schema_editor.execute(f'ALTER TABLE {table} DROP CONSTRAINT {name}')
    for table, name in TARGETS.items():
        schema_editor.execute(f'ALTER TABLE {table} DROP CONSTRAINT {name}')


class Migration(migrations.Migration):
    dependencies = [
        ('purchases', '0008_purchase_company_identity'),
        ('expenses', '0008_chart_company_identity'),
        ('finance', '0008_ledger_company_identity'),
        ('inventory', '0015_owner_ledger_integrity'),
    ]
    operations = [migrations.RunPython(install, uninstall)]
