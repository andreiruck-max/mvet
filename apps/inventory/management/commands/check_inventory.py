from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum, F, Exists, OuterRef
from apps.products.models import Product
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import quant

class Command(BaseCommand):
    help='Confere saldos e valores contra o livro de movimentos, sem alterar dados.'
    def handle(self,*args,**options):
        errors=[]
        if StockMovement.objects.exclude(company_id=F('operation__company_id')).exists():
            errors.append('Empresa do movimento diverge da operação.')
        balances = StockBalance.objects.filter(company_id=OuterRef('company_id'),
            product_id=OuterRef('product_id'),location_id=OuterRef('location_id'))
        if StockMovement.objects.annotate(has_balance=Exists(balances)).filter(has_balance=False).exists():
            errors.append('Há movimento sem saldo local correspondente para empresa/produto/depósito.')
        positions = {}
        for move in StockMovement.objects.order_by('pk').values('company_id','product_id','quantity','value',
                'owner_before_quantity','owner_before_value').iterator(chunk_size=2000):
            key = (move['company_id'],move['product_id'])
            before_q,before_v = positions.get(key,(Decimal(0),Decimal(0)))
            if move['owner_before_quantity'] is not None and (move['owner_before_quantity'],move['owner_before_value']) != (before_q,before_v):
                errors.append(f'Empresa {key[0]}, produto {key[1]}: posição empresarial diverge do histórico acumulado.')
            positions[key] = (before_q+move['quantity'],before_v+move['value'])
        snapshots = StockMovement.objects.filter(owner_before_quantity__isnull=False)
        if snapshots.exclude(owner_after_quantity=F('owner_before_quantity')+F('quantity')).exists():
            errors.append('Snapshot empresarial de quantidade diverge do movimento.')
        if snapshots.exclude(owner_after_value=F('owner_before_value')+F('value')).exists():
            errors.append('Snapshot empresarial de valor diverge do movimento.')
        for p in Product.objects.all():
            ledger=p.movements.aggregate(quantity=Sum('quantity'),value=Sum('value'))
            if p.quantity!=(ledger['quantity'] or 0) or p.value!=(ledger['value'] or 0):errors.append(f'SKU {p.sku}: total diverge do livro.')
            local=p.balances.aggregate(total=Sum('quantity'))['total'] or 0
            if p.quantity!=local:errors.append(f'SKU {p.sku}: total diverge dos locais.')
            costs=p.balances.filter(quantity__gt=0).aggregate(q=Sum('quantity'),v=Sum('value'))
            if not costs['q']:costs=p.balances.filter(quantity__lt=0).aggregate(q=Sum('quantity'),v=Sum('value'))
            if costs['q'] and p.average_cost!=quant(costs['v']/costs['q']):errors.append(f'SKU {p.sku}: custo médio inconsistente.')
        for b in StockBalance.objects.all():
            qty=StockMovement.objects.filter(company_id=b.company_id,product_id=b.product_id,location_id=b.location_id).aggregate(total=Sum('quantity'))['total'] or 0
            local_value=StockMovement.objects.filter(company_id=b.company_id,product_id=b.product_id,location_id=b.location_id).aggregate(total=Sum('value'))['total'] or 0
            if local_value!=b.value:errors.append(f'Saldo {b.pk}: valor local diverge do livro.')
            if b.quantity and b.average_cost!=quant(b.value/b.quantity):errors.append(f'Saldo {b.pk}: custo médio local inconsistente.')
            if not b.quantity and b.value:errors.append(f'Saldo {b.pk}: valor residual sem quantidade.')
            if qty!=b.quantity:errors.append(f'Saldo {b.pk}: quantidade local diverge do livro.')
        if errors:raise CommandError('\n'.join(errors))
        self.stdout.write(self.style.SUCCESS('Estoque conciliado: quantidades, locais, valores e custo médio.'))
