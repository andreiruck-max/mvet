from django.core.management.base import BaseCommand
from apps.notifications.services import refresh


class Command(BaseCommand):
    help = 'Atualiza alertas internos; executar periodicamente pelo agendador do servidor.'

    def handle(self, *args, **options):
        self.stdout.write(f'{refresh()} condições ativas processadas.')
