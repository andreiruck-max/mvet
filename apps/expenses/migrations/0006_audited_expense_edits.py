from django.db import migrations

EXPENSE_GUARD = """
      IF NULLIF(current_setting('mvet.expense_edit',true),'') IS NOT NULL THEN
        IF (to_jsonb(NEW)-ARRAY['description','amount','document_date','competence','supplier_id','counterparty','category_id','category_snapshot','classification','rule_snapshot','cost_center','notes','recurrence_enabled','revision']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['description','amount','document_date','competence','supplier_id','counterparty','category_id','category_snapshot','classification','rule_snapshot','cost_center','notes','recurrence_enabled','revision'])
          OR NEW.revision<>OLD.revision+1 OR NOT EXISTS (
          SELECT 1 FROM expenses_expenserevision r WHERE r.id::text=current_setting('mvet.expense_edit',true)
          AND r.expense_id=OLD.id AND r.number=NEW.revision
          AND r.before->'expense'=jsonb_build_object('description',OLD.description,'amount',OLD.amount::text,'document_date',OLD.document_date::text,'competence',OLD.competence::text,'supplier_id',OLD.supplier_id,'counterparty',OLD.counterparty,'category_id',OLD.category_id,'category_snapshot',OLD.category_snapshot,'classification',OLD.classification,'rule_snapshot',OLD.rule_snapshot,'cost_center',OLD.cost_center,'notes',OLD.notes,'recurrence_enabled',OLD.recurrence_enabled,'revision',OLD.revision) AND r.after->'expense'=jsonb_build_object('description',NEW.description,'amount',NEW.amount::text,'document_date',NEW.document_date::text,'competence',NEW.competence::text,'supplier_id',NEW.supplier_id,'counterparty',NEW.counterparty,'category_id',NEW.category_id,'category_snapshot',NEW.category_snapshot,'classification',NEW.classification,'rule_snapshot',NEW.rule_snapshot,'cost_center',NEW.cost_center,'notes',NEW.notes,'recurrence_enabled',NEW.recurrence_enabled,'revision',NEW.revision)
          AND ((NEW.title_id IS NULL AND r.after->'title'='null'::jsonb) OR EXISTS(
            SELECT 1 FROM finance_financialtitle t WHERE t.id=NEW.title_id AND r.after->'title'=jsonb_build_object('amount',t.amount::text,'description',t.description,'counterparty',t.counterparty,'date',t.date::text,'due_date',t.due_date::text,'account_id',t.account_id,'revision',t.revision)
            AND t.amount=NEW.amount AND t.date=NEW.document_date)))
        THEN RAISE EXCEPTION 'Expense edit requires matching audited revision and obligation'; END IF;
        RETURN NEW;
      END IF;
"""
TITLE_GUARD = """
      IF NULLIF(current_setting('mvet.expense_edit',true),'') IS NOT NULL THEN
        IF OLD.status<>'OPEN' OR (to_jsonb(NEW)-ARRAY['amount','description','counterparty','date','due_date','account_id','revision']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['amount','description','counterparty','date','due_date','account_id','revision'])
          OR NEW.revision<>OLD.revision+1 OR NEW.amount<NEW.settled OR NEW.due_date<NEW.date
          OR EXISTS(SELECT 1 FROM finance_financialoperation o WHERE o.title_id=OLD.id AND o.kind='SETTLEMENT'
            AND o.date<NEW.date AND NOT EXISTS(SELECT 1 FROM finance_financialoperation r WHERE r.reversal_of_id=o.id))
          OR NOT EXISTS(SELECT 1 FROM expenses_expenserevision r JOIN expenses_expense e ON e.id=r.expense_id
            WHERE r.id::text=current_setting('mvet.expense_edit',true) AND e.title_id=OLD.id AND e.status='ACTIVE'
            AND r.number=e.revision+1 AND r.before->'title'=jsonb_build_object('amount',OLD.amount::text,'description',OLD.description,'counterparty',OLD.counterparty,'date',OLD.date::text,'due_date',OLD.due_date::text,'account_id',OLD.account_id,'revision',OLD.revision) AND r.after->'title'=jsonb_build_object('amount',NEW.amount::text,'description',NEW.description,'counterparty',NEW.counterparty,'date',NEW.date::text,'due_date',NEW.due_date::text,'account_id',NEW.account_id,'revision',NEW.revision))
        THEN RAISE EXCEPTION 'Expense obligation edit requires matching revision'; END IF;
        RETURN NEW;
      END IF;
"""


def guards(apps, schema_editor, reverse=False):
    if schema_editor.connection.vendor != 'postgresql': return
    for name, anchor, block in [
        ('mvet_expense_protected', "      IF (to_jsonb(NEW)-ARRAY['category_id'", EXPENSE_GUARD),
        ('mvet_finance_title', "      IF OLD.status='CANCELLED'", TITLE_GUARD),
    ]:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute('SELECT pg_get_functiondef(%s::regprocedure)', [name+'()'])
            definition=cursor.fetchone()[0]
        if reverse: definition=definition.replace(block,'')
        else:
            if anchor not in definition: raise RuntimeError('Expense guard anchor missing: '+name)
            definition=definition.replace(anchor,block+anchor,1)
        schema_editor.execute(definition)


def restore(apps,schema_editor):guards(apps,schema_editor,reverse=True)


class Migration(migrations.Migration):
    dependencies=[('expenses','0005_expense_expense_noncash_category'),('finance','0004_cancel_reversed_direct_entries')]
    operations=[migrations.RunPython(guards,restore)]
