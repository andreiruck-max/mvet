"""Read-only evidence for a disputed stock snapshot; never adjusts balances."""
import json
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum, Count
from apps.inventory.models import StockBalance, StockMovement, InventoryReconciliation


class Command(BaseCommand):
    help = 'Consulta saldos, conciliações e movimentos posteriores à data-base, sem gravar.'

    def add_arguments(self, parser):
        parser.add_argument('--date', required=True)

    def handle(self, *args, **options):
        try:
            day = date.fromisoformat(options['date'])
        except ValueError as exc:
            raise CommandError('Use --date AAAA-MM-DD.') from exc
        records = []
        for record in InventoryReconciliation.objects.filter(base_date__gte=day).order_by('pk'):
            records.append(dict(id=record.pk, base_date=record.base_date, applied_at=record.created_at,
                                digest=record.digest, locations=record.report.get('locations', [])))
        balances = list(StockBalance.objects.order_by('location__name').values('location_id','location__name')
                        .annotate(quantity=Sum('quantity'),value=Sum('value'),positions=Count('pk')))
        movements = list(StockMovement.objects.filter(operation__date__gt=day)
                         .order_by('operation__date','location__name','operation__kind')
                         .values('operation__date','location__name','operation__kind')
                         .annotate(quantity=Sum('quantity'),value=Sum('value'),movements=Count('pk')))
        late = []
        matching = InventoryReconciliation.objects.filter(base_date=day).first()
        if matching:
            late = list(StockMovement.objects.filter(operation__created_at__gt=matching.created_at, operation__date__lte=day)
                        .order_by('location__name','operation__kind').values('location__name','operation__kind')
                        .annotate(quantity=Sum('quantity'),value=Sum('value'),movements=Count('pk')))
        self.stdout.write(json.dumps(dict(base_date=day, current_balances=balances, reconciliations=records,
                          movements_after_base=movements, backdated_after_reconciliation=late),default=str,ensure_ascii=False,indent=2))
