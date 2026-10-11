import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.management.base import BaseCommand, CommandError
from apps.inventory.reconciliation import reconcile


class Command(BaseCommand):
    help = 'Confere posição JSON; aplica diferenças auditadas com --commit --revision da prévia.'

    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--username', required=True)
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--revision')

    def handle(self, *args, **options):
        try:
            actor = get_user_model().objects.get(username=options['username'], is_active=True)
            report = reconcile(actor=actor, raw=Path(options['file']).read_bytes(), commit=options['commit'], expected_revision=options['revision'])
        except (ValidationError, PermissionDenied, get_user_model().DoesNotExist, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
