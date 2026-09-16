import json
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from apps.inventory.importing import load_opening
class Command(BaseCommand):
    help='Valida estoque XLSX. Sem --commit apenas apresenta relatório; não altera dados.'
    def add_arguments(self,parser):
        parser.add_argument('file')
        parser.add_argument('--actor',required=True,type=int)
        parser.add_argument('--location',default='Estoque inicial')
        parser.add_argument('--merge-duplicates',action='store_true')
        parser.add_argument('--commit',action='store_true')
    def handle(self,*args,**options):
        try:
            actor=get_user_model().objects.get(pk=options['actor'])
            report=load_opening(actor=actor,path=options['file'],location_name=options['location'],merge_duplicates=options['merge_duplicates'],commit=options['commit'])
        except (ValidationError, get_user_model().DoesNotExist) as exc:raise CommandError(str(exc))
        self.stdout.write(json.dumps(report,ensure_ascii=False,indent=2))
        if report['errors']:raise CommandError('Carga bloqueada pelas inconsistências acima; nenhum dado alterado.')
