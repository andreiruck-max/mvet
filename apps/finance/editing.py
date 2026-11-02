"""Audited obligation corrections. Existing cash and origin documents stay historical."""
from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from apps.accounts.access import master
from apps.core.models import Company
from apps.core.services import audit
from apps.inventory.services import domain_lock, number
from .models import FinancialTitle as Title, FinancialTitleRevision
from .services import CENT, account_for, validate_date

FIELDS = ['direction','description','counterparty','date','due_date','amount','account_id','category','opening','notes','revision']
LABELS = dict(direction='Tipo',description='Descrição',counterparty='Favorecido / cliente',date='Data de origem',due_date='Vencimento',amount='Valor',account_id='Conta prevista (ID)',category='Classificação',opening='Pendência de abertura',notes='Observação')


def snapshot(title):
    return {key:str(value) if isinstance(value,(date,Decimal)) else value for key in FIELDS for value in [getattr(title,key)]}


@transaction.atomic
def edit_title(*, actor, pk, revision, reason, data):
    master(actor);domain_lock()
    title=Title.objects.select_for_update().get(pk=pk)
    if title.status!='OPEN' or title.revision!=revision:
        raise ValidationError('Título cancelado ou alterado por outra operação. Reabra a edição.')
    if title.source=='expense' or hasattr(title,'expense'):
        raise ValidationError('Edite a despesa de origem para manter valor, categoria e obrigação sincronizados.')
    if not reason.strip() or len(reason)>500:raise ValidationError('Informe o motivo da edição (até 500 caracteres).')
    if set(data)!=(set(FIELDS)-{'account_id','revision'}|{'account'}):raise ValidationError('Informe todos os campos editáveis do título.')
    data={**data,'amount':number(data['amount'],CENT)}
    if title.purchase_installment_id or title.sale_id or title.source!='manual':
        if data['direction']!=title.direction or data['opening']!=title.opening:
            raise ValidationError('Tipo pagar/receber e abertura pertencem ao documento de origem.')
    if title.operations.exists() and (data['direction']!=title.direction or data['opening']!=title.opening):
        raise ValidationError('Título com histórico bancário não permite trocar pagar/receber ou abertura.')
    cutoff=Company.objects.get(pk=1).cutover_date
    if data['opening']:
        if data['date']>=cutoff:raise ValidationError('Pendência de abertura exige origem anterior ao corte.')
        data['category']='OPENING'
    else:
        validate_date(data['date'],future=True)
        if data['category']=='OPENING':raise ValidationError('Classificação de abertura exige pendência anterior ao corte.')
    if data['due_date']<data['date']:raise ValidationError('Vencimento anterior à origem.')
    if data['amount']<title.settled:raise ValidationError('Valor menor que o principal liquidado. Estorne a baixa incorreta antes de reduzir.')
    if not data['opening'] and title.operations.filter(kind='SETTLEMENT',reversal__isnull=True,date__lt=data['date']).exists():
        raise ValidationError('Origem não pode ficar após uma baixa existente.')
    if title.purchase_installment_id and not data['counterparty'].strip():
        data['counterparty']=str(title.purchase_installment.purchase.supplier)
    if data['account']:
        account_for(data['account'].pk,max(cutoff,data['due_date']),active=data['account'].pk!=title.account_id)
    before=snapshot(title)
    for key,value in data.items():setattr(title,key,value)
    title.revision+=1;title.full_clean()
    after=snapshot(title)
    entry=FinancialTitleRevision.objects.create(title=title,number=title.revision,actor=actor,reason=reason.strip(),before=before,after=after)
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.title_edit',%s,true)",[str(entry.pk)])
    try:
        with transaction.atomic():title.save(update_fields=FIELDS)
    finally:
        if connection.vendor=='postgresql':
            with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.title_edit','',true)")
    audit(actor,title,'edit_financial_title',before,{**after,'reason':reason.strip()})
    return title
