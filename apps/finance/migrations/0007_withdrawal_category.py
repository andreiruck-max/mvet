from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('finance', '0006_duepayment')]
    operations = [migrations.AlterField(
        model_name='financialtitle', name='category',
        field=models.CharField(choices=[('OPERATING','Operacional'),('FINANCIAL','Financeiro / juros'),('PRINCIPAL','Patrimonial / principal'),('WITHDRAWAL','Retirada / distribuição de sócio'),('OPENING','Pendência de abertura'),('OTHER','A classificar')], default='OTHER', max_length=20, verbose_name='Classificação gerencial'))]
