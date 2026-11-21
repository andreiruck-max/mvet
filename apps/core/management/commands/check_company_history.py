"""Read-only fingerprints for the staged company attribution migrations."""
import hashlib
import json
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction


DOMAINS = {
    'core', 'accounts', 'products', 'inventory', 'sales', 'purchases',
    'finance', 'expenses', 'commissions', 'crm', 'integrations', 'notifications',
}


def inventory():
    return {model._meta.label_lower: model for model in apps.get_models()
            if model._meta.app_label in DOMAINS and model._meta.managed
            and not model._meta.proxy}


def fingerprint(model, fields):
    digest = hashlib.sha256()
    count = 0
    for row in model._base_manager.order_by(model._meta.pk.attname).values_list(*fields).iterator(chunk_size=2000):
        encoded = json.dumps(row, cls=DjangoJSONEncoder, sort_keys=True,
                             ensure_ascii=True, separators=(',', ':')).encode()
        digest.update(len(encoded).to_bytes(8, 'big'))
        digest.update(encoded)
        count += 1
    return {'fields': fields, 'count': count, 'sha256': digest.hexdigest()}


class Command(BaseCommand):
    help = 'Registra/compara histórico por hashes, sem alterar dados (somente PostgreSQL).'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--baseline', type=Path)
        group.add_argument('--compare', type=Path)

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError('A verificação exige PostgreSQL.')
        models = inventory()
        baseline = None
        if options['compare']:
            try:
                baseline = json.loads(options['compare'].read_text())
                if baseline['version'] != 1 or not baseline['models']:
                    raise ValueError()
                for label, record in baseline['models'].items():
                    if label not in models:
                        raise ValueError()
                    available = {f.attname for f in models[label]._meta.concrete_fields}
                    if not record['fields'] or not set(record['fields']) <= available:
                        raise ValueError()
            except (OSError, ValueError, KeyError, TypeError):
                raise CommandError('Baseline inválido ou schema histórico incompatível.')
        snapshot = {'version': 1, 'models': {}}
        differences = []
        # One consistent database snapshot; no writes, trigger changes or migrations.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            labels = sorted(baseline['models'] if baseline else models)
            for label in labels:
                model = models[label]
                fields = (baseline['models'][label]['fields'] if baseline else
                          sorted(f.attname for f in model._meta.concrete_fields))
                record = fingerprint(model, fields)
                snapshot['models'][label] = record
                if baseline and record != baseline['models'][label]:
                    differences.append(label)
                # Newly added ownership must attribute every historical row to Mercadovet.
                available = {f.attname for f in model._meta.concrete_fields}
                if baseline and 'company_id' in available and 'company_id' not in fields:
                    if model._base_manager.exclude(company_id=1).exists():
                        differences.append(label + ': empresa histórica diferente de Mercadovet')
        if options['baseline']:
            try:
                with options['baseline'].open('x') as output:
                    json.dump(snapshot, output, ensure_ascii=True, sort_keys=True, indent=2)
            except OSError as exc:
                raise CommandError('Não foi possível criar o baseline; arquivo existente não será substituído.') from exc
            self.stdout.write(self.style.SUCCESS(f'Baseline criado: {len(snapshot["models"])} modelos.'))
        elif differences:
            raise CommandError('Divergências no histórico: ' + ', '.join(differences))
        else:
            self.stdout.write(self.style.SUCCESS(f'Histórico preservado: {len(snapshot["models"])} modelos; zero diferenças.'))
