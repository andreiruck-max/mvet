import json
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.management.base import BaseCommand, CommandError
from apps.inventory.location_import import load_snapshot


class Command(BaseCommand):
    help = 'Valida posição inicial JSON por depósito; grava somente com --commit.'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--username', required=True)
        parser.add_argument('--commit', action='store_true')

    def handle(self, *args, **options):
        try:
            actor = get_user_model().objects.get(username=options['username'], is_active=True)
            report = load_snapshot(actor=actor, path=options['file'], commit=options['commit'])
        except (ValidationError, PermissionDenied, get_user_model().DoesNotExist, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
