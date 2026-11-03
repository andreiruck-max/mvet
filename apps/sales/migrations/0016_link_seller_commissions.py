from django.db import migrations
import unicodedata


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c)).casefold().split())


def link_existing(apps,schema_editor):
    Channel=apps.get_model('sales','SalesChannel')
    Payee=apps.get_model('commissions','Payee')
    alias=schema_editor.connection.alias
    for channel_name,payee_name in [('[VENDEDOR] CESAR','CESAR OLIVEIRA'),('[VENDEDOR] LUCAS','LUCAS ABRANCHES')]:
        channels=[c for c in Channel.objects.using(alias).filter(active=True,commission_payee__isnull=True) if normalized(c.name)==normalized(channel_name)]
        payees=[p for p in Payee.objects.using(alias).filter(active=True) if normalized(p.name)==normalized(payee_name)]
        if len(channels)==1 and len(payees)==1:
            Channel.objects.using(alias).filter(pk=channels[0].pk,commission_payee__isnull=True).update(commission_payee_id=payees[0].pk)
        else:
            print(f'Comissões: confira o vínculo de {channel_name} em Canais de venda (cadastro ausente, duplicado ou já vinculado).')


class Migration(migrations.Migration):
    dependencies=[('sales','0015_sale_commission_manual_total_sale_commission_payee_and_more')]
    operations=[migrations.RunPython(link_existing,migrations.RunPython.noop)]
