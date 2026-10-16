"""Repair only unmodified synthetic obligations left by direct-entry reversals."""
from uuid import uuid5
from django.db import migrations


def repair(apps, schema_editor):
    Title = apps.get_model('finance', 'FinancialTitle')
    Operation = apps.get_model('finance', 'FinancialOperation')
    Audit = apps.get_model('core', 'AuditLog')
    alias = schema_editor.connection.alias
    # Revision 2 = original settlement + reversal. Rescheduled/reused titles
    # are intentionally excluded: their current intent cannot be inferred.
    titles = Title.objects.using(alias).filter(status='OPEN', source='manual', opening=False,
        settled=0, revision=2, purchase_installment__isnull=True, sale__isnull=True, expense__isnull=True)
    for title in titles.iterator():
        operations = Operation.objects.using(alias).filter(title_id=title.pk, kind='SETTLEMENT')
        if operations.count() != 1:
            continue
        original = operations.first()
        if original.key != uuid5(title.key, 'account-entry-settlement') or original.principal != title.amount:
            continue
        reversal = Operation.objects.using(alias).filter(reversal_of_id=original.pk, kind='REVERSAL', status='POSTED').first()
        if not reversal:
            continue
        title.status = 'CANCELLED'
        title.revision += 1
        title.save(using=alias, update_fields=['status', 'revision'])
        Audit.objects.using(alias).create(actor_id=reversal.actor_id, entity='finance.FinancialTitle',
            entity_id=str(title.pk), operation='repair_reversed_account_entry',
            before={'status': 'OPEN', 'revision': 2},
            after={'status': 'CANCELLED', 'revision': title.revision, 'operation_id': original.pk,
                   'reversal_id': reversal.pk, 'reason': 'Remove previsão indevida de lançamento direto já estornado; livro bancário preservado.'})


class Migration(migrations.Migration):
    dependencies = [('finance', '0003_ledger_protection'), ('expenses', '0001_initial')]
    operations = [migrations.RunPython(repair, migrations.RunPython.noop)]
