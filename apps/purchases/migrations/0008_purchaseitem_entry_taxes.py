# Additive migration; historic purchase lines receive zero tax amounts.
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('purchases', '0007_purchase_account')]

    operations = [
        migrations.AddField(
            model_name='purchaseitem',
            name='ncm',
            field=models.CharField(blank=True, max_length=8, verbose_name='NCM fiscal'),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='ipi',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, validators=[django.core.validators.MinValueValidator(0)], verbose_name='IPI na NF (R$)'),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='st',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, validators=[django.core.validators.MinValueValidator(0)], verbose_name='ICMS-ST de entrada, fora da NF (R$)'),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='difal',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, validators=[django.core.validators.MinValueValidator(0)], verbose_name='DIFAL de entrada, fora da NF (R$)'),
        ),
    ]
