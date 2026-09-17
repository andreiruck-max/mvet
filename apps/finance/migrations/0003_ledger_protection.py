from django.db import migrations


def install(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql': return
    schema_editor.execute("""
    CREATE FUNCTION mvet_finance_immutable() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'Immutable cash ledger: use a reversal'; END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER finance_entry_immutable BEFORE UPDATE OR DELETE ON finance_financialentry FOR EACH ROW EXECUTE FUNCTION mvet_finance_immutable();
    CREATE FUNCTION mvet_finance_operation() RETURNS trigger AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Financial operation cannot be deleted'; END IF;
      IF OLD.status<>'PLANNED' OR OLD.kind<>'TRANSFER' OR NEW.status NOT IN ('POSTED','CANCELLED')
        OR (to_jsonb(NEW)-ARRAY['date','status']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['date','status'])
      THEN RAISE EXCEPTION 'Financial operation is immutable'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER finance_operation_immutable BEFORE UPDATE OR DELETE ON finance_financialoperation FOR EACH ROW EXECUTE FUNCTION mvet_finance_operation();
    CREATE FUNCTION mvet_finance_title() RETURNS trigger AS $$
    DECLARE paid numeric;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Cancel financial titles'; END IF;
      IF OLD.status='CANCELLED' OR NEW.status NOT IN ('OPEN','CANCELLED') OR
        (to_jsonb(NEW)-ARRAY['due_date','account_id','notes','revision','settled','status']) IS DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['due_date','account_id','notes','revision','settled','status'])
      THEN RAISE EXCEPTION 'Financial title principal/origin is immutable'; END IF;
      SELECT COALESCE(SUM(o.principal),0) INTO paid FROM finance_financialoperation o
        WHERE o.title_id=OLD.id AND o.kind='SETTLEMENT' AND o.status='POSTED'
        AND NOT EXISTS(SELECT 1 FROM finance_financialoperation r WHERE r.reversal_of_id=o.id);
      IF NEW.settled<>paid OR (NEW.status='CANCELLED' AND paid<>0)
      THEN RAISE EXCEPTION 'Title settlement must reconcile with ledger'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER finance_title_protected BEFORE UPDATE OR DELETE ON finance_financialtitle FOR EACH ROW EXECUTE FUNCTION mvet_finance_title();
    CREATE FUNCTION mvet_finance_account() RETURNS trigger AS $$
    BEGIN
      IF (NEW.opening_balance<>OLD.opening_balance OR NEW.opening_date<>OLD.opening_date) AND
        (EXISTS(SELECT 1 FROM finance_financialentry WHERE account_id=OLD.id) OR EXISTS(SELECT 1 FROM finance_financialtitle WHERE account_id=OLD.id))
      THEN RAISE EXCEPTION 'Used account opening is immutable'; END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER finance_account_opening BEFORE UPDATE ON finance_financialaccount FOR EACH ROW EXECUTE FUNCTION mvet_finance_account();
    CREATE FUNCTION mvet_finance_balanced() RETURNS trigger AS $$
    DECLARE op finance_financialoperation; n integer; total numeric; positive numeric; sign numeric;
    BEGIN
      IF TG_TABLE_NAME='finance_financialentry' THEN
        SELECT * INTO op FROM finance_financialoperation WHERE id=NEW.operation_id;
      ELSE SELECT * INTO op FROM finance_financialoperation WHERE id=NEW.id; END IF;
      SELECT COUNT(*),COALESCE(SUM(amount),0),COALESCE(SUM(amount) FILTER(WHERE amount>0),0)
        INTO n,total,positive FROM finance_financialentry WHERE operation_id=op.id;
      IF op.kind='TRANSFER' AND (n<>2 OR total<>0 OR positive<>op.actual OR op.actual<=0)
      THEN RAISE EXCEPTION 'Transfer must have two balanced legs'; END IF;
      IF op.kind='SETTLEMENT' THEN
        SELECT CASE WHEN direction='PAY' THEN -1 ELSE 1 END INTO sign FROM finance_financialtitle WHERE id=op.title_id;
        IF sign IS NULL OR op.status<>'POSTED' OR total<>sign*op.actual OR n<>(CASE WHEN op.actual=0 THEN 0 ELSE 1 END)
          OR op.actual<>op.principal+op.interest-op.discount
        THEN RAISE EXCEPTION 'Settlement must reconcile'; END IF;
      END IF;
      IF op.kind='REVERSAL' THEN
        IF op.reversal_of_id IS NULL OR EXISTS(
          SELECT account_id,SUM(amount) FROM finance_financialentry WHERE operation_id IN (op.id,op.reversal_of_id)
          GROUP BY account_id HAVING SUM(amount)<>0)
        THEN RAISE EXCEPTION 'Reversal must offset original legs'; END IF;
      END IF;
      RETURN NULL;
    END; $$ LANGUAGE plpgsql;
    CREATE CONSTRAINT TRIGGER finance_balanced_operation AFTER INSERT OR UPDATE ON finance_financialoperation DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mvet_finance_balanced();
    CREATE CONSTRAINT TRIGGER finance_balanced_entry AFTER INSERT ON finance_financialentry DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mvet_finance_balanced();
    """)


def uninstall(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql': return
    schema_editor.execute("""
    DROP TRIGGER finance_balanced_entry ON finance_financialentry;
    DROP TRIGGER finance_balanced_operation ON finance_financialoperation;
    DROP TRIGGER finance_account_opening ON finance_financialaccount;
    DROP TRIGGER finance_title_protected ON finance_financialtitle;
    DROP TRIGGER finance_operation_immutable ON finance_financialoperation;
    DROP TRIGGER finance_entry_immutable ON finance_financialentry;
    DROP FUNCTION mvet_finance_balanced(); DROP FUNCTION mvet_finance_account(); DROP FUNCTION mvet_finance_title();
    DROP FUNCTION mvet_finance_operation(); DROP FUNCTION mvet_finance_immutable();
    """)


class Migration(migrations.Migration):
    dependencies=[('finance','0002_backfill_titles')]
    operations=[migrations.RunPython(install,uninstall)]
