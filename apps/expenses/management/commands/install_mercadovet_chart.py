from django.core.management.base import BaseCommand
from apps.expenses.chart import install_chart


class Command(BaseCommand):
    help = 'Instala o plano Mercadovet sem sobrescrever categorias ou lançamentos existentes.'

    def handle(self, *args, **options):
        created = install_chart()
        self.stdout.write(self.style.SUCCESS(f'Plano Mercadovet: {created} categorias criadas. Histórico preservado.'))
