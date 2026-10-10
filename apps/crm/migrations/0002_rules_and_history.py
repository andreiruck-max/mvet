from django.db import migrations

RESULTS=['INTERESTED','NOT_NOW','CALLBACK','QUOTE_REQUEST','QUOTE_SENT','NEGOTIATION','SALE','WAITING','NO_REPLY','READ_NO_REPLY','NO_ANSWER','INVALID','WRONG_NUMBER','OUTSIDE','OPT_OUT','COLD','OTHER']

def seed(apps,schema_editor):
    Rule=apps.get_model('crm','RecurrenceRule')
    days={'NOT_NOW':30,'QUOTE_SENT':3,'QUOTE_REQUEST':3,'READ_NO_REPLY':15,'COLD':60,'WAITING':3}
    for result in RESULTS:Rule.objects.get_or_create(result=result,defaults={'days':days.get(result,7),'allow_manual':result!='OPT_OUT'})

def protect(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute('''CREATE FUNCTION mvet_crm_history_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'CRM history is immutable; record a new event'; END; $$;
    CREATE TRIGGER crm_interaction_immutable BEFORE UPDATE OR DELETE ON crm_interaction FOR EACH ROW EXECUTE FUNCTION mvet_crm_history_immutable();
    CREATE TRIGGER crm_event_immutable BEFORE UPDATE OR DELETE ON crm_contactevent FOR EACH ROW EXECUTE FUNCTION mvet_crm_history_immutable();''')

def unprotect(apps,schema_editor):
    if schema_editor.connection.vendor!='postgresql':return
    schema_editor.execute('''DROP TRIGGER IF EXISTS crm_interaction_immutable ON crm_interaction;
    DROP TRIGGER IF EXISTS crm_event_immutable ON crm_contactevent;
    DROP FUNCTION IF EXISTS mvet_crm_history_immutable();''')

class Migration(migrations.Migration):
    dependencies=[('crm','0001_initial')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop),migrations.RunPython(protect,unprotect)]
