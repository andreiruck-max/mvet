from datetime import date
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from apps.integrations.bling import sync_page


class Command(BaseCommand):
    help = 'Consulta NF do Bling para conferência, sem confirmar vendas. Reexecução é idempotente.'

    def add_arguments(self, parser):
        parser.add_argument('--user', required=True, help='Login de usuário ativo autorizado')
        parser.add_argument('--start', required=True, type=date.fromisoformat)
        parser.add_argument('--end', required=True, type=date.fromisoformat)
        parser.add_argument('--page', type=int, default=1)
        parser.add_argument('--pages', type=int, default=1, help='Máximo de páginas, até 100')
        parser.add_argument('--status', type=int, choices=[2, 5], default=5)

    def handle(self, *args, **options):
        if not 1 <= options['pages'] <= 100: raise CommandError('Informe de 1 a 100 páginas.')
        actor = get_user_model().objects.filter(username=options['user'], is_active=True).first()
        if actor is None: raise CommandError('Usuário ativo não encontrado.')
        for page in range(options['page'], options['page'] + options['pages']):
            try:
                run = sync_page(actor=actor, start=options['start'], end=options['end'], page=page, source_status=options['status'])
            except (PermissionDenied, ValidationError):
                raise CommandError('Consulta não autorizada, desconectada ou parâmetros inválidos.') from None
            self.stdout.write(f'Página {page}: {run.processed} consultadas, {run.errors} erros.')
            if run.errors: raise CommandError(f'Consulta parcial. Confira a fila/lote {run.pk} e reexecute a página {page}.')
            if not run.has_more: break
