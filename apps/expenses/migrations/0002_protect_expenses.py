from django.db import migrations


def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute("""
    CREATE FUNCTION mvet_expense_revision_immutable() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'Expense revision is immutable'; END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER expense_revision_immutable BEFORE UPDATE OR DELETE ON expenses_expenserevision
      FOR EACH ROW EXECUTE FUNCTION mvet_expense_revision_immutable();
    CREATE FUNCTION mvet_expense_protected() RETURNS trigger AS $$
    DECLARE previous jsonb; current_value jsonb;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Cancel expenses instead of deleting'; END IF;
      IF OLD.status='CANCELLED' THEN RAISE EXCEPTION 'Cancelled expense is immutable'; END IF;
      IF (to_jsonb(NEW)-ARRAY['category_id','category_snapshot','classification','rule_snapshot','cost_center','revision','status','cancelled_at','cancellation_reason','recurrence_enabled'])
        IS DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['category_id','category_snapshot','classification','rule_snapshot','cost_center','revision','status','cancelled_at','cancellation_reason','recurrence_enabled'])
      THEN RAISE EXCEPTION 'Expense amount, accrual and origin are immutable'; END IF;
      IF NEW.status='CANCELLED' AND NOT EXISTS(SELECT 1 FROM finance_financialtitle WHERE id=NEW.title_id AND status='CANCELLED' AND settled=0)
      THEN RAISE EXCEPTION 'Cancel financial obligation first'; END IF;
      previous=jsonb_build_object('category_id',OLD.category_id,'category_snapshot',OLD.category_snapshot,'classification',OLD.classification,'rule_snapshot',OLD.rule_snapshot,'cost_center',OLD.cost_center);
      current_value=jsonb_build_object('category_id',NEW.category_id,'category_snapshot',NEW.category_snapshot,'classification',NEW.classification,'rule_snapshot',NEW.rule_snapshot,'cost_center',NEW.cost_center);
      IF previous IS DISTINCT FROM current_value AND NOT EXISTS(
        SELECT 1 FROM expenses_expenserevision WHERE expense_id=OLD.id AND number=NEW.revision AND before=previous AND after=current_value)
      THEN RAISE EXCEPTION 'Classification change requires matching revision'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER expense_history_protected BEFORE UPDATE OR DELETE ON expenses_expense
      FOR EACH ROW EXECUTE FUNCTION mvet_expense_protected();
    """)


def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute('DROP TRIGGER expense_history_protected ON expenses_expense; DROP TRIGGER expense_revision_immutable ON expenses_expenserevision; DROP FUNCTION mvet_expense_protected(); DROP FUNCTION mvet_expense_revision_immutable();')


class Migration(migrations.Migration):
    dependencies=[('expenses','0001_initial')]
    operations=[migrations.RunPython(install,uninstall)]
