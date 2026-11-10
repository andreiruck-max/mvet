import signal
from threading import Event
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connections
from apps.integrations.scheduling import tick


class Command(BaseCommand):
    help = 'Executa a busca periódica de notas Bling em processo separado; nunca confirma documentos.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        stop = Event()
        if not options['once']:
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
            signal.signal(signal.SIGINT, lambda *_: stop.set())
        while not stop.is_set():
            close_old_connections()
            try:
                tick()
            except Exception:
                # No credentials, payloads or customer data in container logs.
                connections.close_all()
                self.stderr.write('Busca automática indisponível; nova tentativa em 10 segundos. Confira banco, migrações e configuração.')
                if options['once']:
                    raise
            if options['once']:
                return
            stop.wait(10)
