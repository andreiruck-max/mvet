from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from apps.notifications.services import record_backup


class Command(BaseCommand):
    help = 'Registra evidência produzida pelo script de backup. Não executa nem restaura o backup.'

    def add_arguments(self, parser):
        parser.add_argument('status', choices=['success', 'failure'])
        parser.add_argument('--size', type=int, default=0)
        parser.add_argument('--sha256', default='')

    def handle(self, *args, **options):
        try:
            record_backup(success=options['status'] == 'success', size_bytes=options['size'], sha256=options['sha256'])
        except ValidationError as error:
            raise CommandError('; '.join(error.messages)) from error
        self.stdout.write('Evidência de backup registrada.')
