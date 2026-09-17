from django.db import migrations


def backfill(apps,schema_editor):
    Title=apps.get_model('finance','FinancialTitle')
    Installment=apps.get_model('purchases','PurchaseInstallment')
    Sale=apps.get_model('sales','Sale')
    for i in Installment.objects.filter(status='PENDING',purchase__status__in=['ORDERED','RECEIVED']).select_related('purchase__supplier').iterator():
        p=i.purchase
        Title.objects.get_or_create(purchase_installment_id=i.pk,defaults=dict(direction='PAY',description=f'Compra {p.document} · parcela {i.number}',counterparty=p.supplier.trade_name or p.supplier.legal_name,date=p.date,due_date=i.due_date,amount=i.amount,actor_id=p.confirmed_by_id or p.created_by_id,source='purchase',category='PRINCIPAL'))
    for sale in Sale.objects.filter(status='CONFIRMED').iterator():
        amount=sale.products_amount-sale.discount+sale.shipping_received
        if amount>0:
            Title.objects.get_or_create(sale_id=sale.pk,defaults=dict(direction='RECEIVE',description=f'Venda NF {sale.invoice_number}/{sale.invoice_series}',date=sale.date,due_date=sale.date,amount=amount,actor_id=sale.confirmed_by_id or sale.created_by_id,source='sale',category='OPERATING'))


class Migration(migrations.Migration):
    dependencies=[('finance','0001_initial')]
    operations=[migrations.RunPython(backfill,migrations.RunPython.noop)]
