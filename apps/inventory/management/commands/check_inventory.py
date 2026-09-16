from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from apps.products.models import Product
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import quant

class Command(BaseCommand):
    help='Confere saldos e valores contra o livro de movimentos, sem alterar dados.'
    def handle(self,*args,**options):
        errors=[]
        for p in Product.objects.all():
            ledger=p.movements.aggregate(quantity=Sum('quantity'),value=Sum('value'))
            if p.quantity!=(ledger['quantity'] or 0) or p.value!=(ledger['value'] or 0):errors.append(f'SKU {p.sku}: total diverge do livro.')
            local=p.balances.aggregate(total=Sum('quantity'))['total'] or 0
            if p.quantity!=local:errors.append(f'SKU {p.sku}: total diverge dos locais.')
            if p.quantity and p.average_cost!=quant(p.value/p.quantity):errors.append(f'SKU {p.sku}: custo médio inconsistente.')
        for b in StockBalance.objects.all():
            qty=StockMovement.objects.filter(product_id=b.product_id,location_id=b.location_id).aggregate(total=Sum('quantity'))['total'] or 0
            if qty!=b.quantity:errors.append(f'Saldo {b.pk}: quantidade local diverge do livro.')
        if errors:raise CommandError('\n'.join(errors))
        self.stdout.write(self.style.SUCCESS('Estoque conciliado: quantidades, locais, valores e custo médio.'))
