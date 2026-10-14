from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('commissions', '0004_allocation_commission_allocation_nonzero_and_more'),
        ('sales', '0012_protect_sale_context_correction'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='seller',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='sales', to='commissions.payee', verbose_name='Vendedor / comissionado'),
        ),
    ]
