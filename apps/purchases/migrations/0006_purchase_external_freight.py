import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('purchases', '0005_purchaseitem_discount_and_more')]
    operations = [
        migrations.AddField(
            model_name='purchase', name='external_freight',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name='Frete pago à transportadora fora da nota (R$)'),
        ),
    ]
