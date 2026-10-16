"""Audited corrections of expense data and its obligation; never rewrite cash."""
from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from apps.accounts.access import master
from apps.core.models import Company
from apps.core.services import audit
from apps.finance.models import FinancialTitle
from apps.finance.services import account_for
from apps.inventory.services import domain_lock, number
from .models import Expense, ExpenseRevision
from .services import classify, CENT

EXPENSE_FIELDS = ['description','amount','document_date','competence','supplier_id','counterparty',
    'category_id','category_snapshot','classification','rule_snapshot','cost_center','notes','recurrence_enabled','revision']
TITLE_FIELDS = ['amount','description','counterparty','date','due_date','account_id','revision']


def snapshot(obj, fields):
    return {field: str(value) if isinstance(value, (Decimal, date)) else value
            for field in fields for value in [getattr(obj, field)]}


def edit_snapshot(obj, title):
    return {'expense': snapshot(obj, EXPENSE_FIELDS), 'title': snapshot(title, TITLE_FIELDS) if title else None}


@transaction.atomic
def edit_expense(*, actor, pk, revision, title_revision, reason, data):
    master(actor);domain_lock()
    obj=Expense.objects.select_for_update().get(pk=pk)
    title=FinancialTitle.objects.select_for_update().get(pk=obj.title_id) if obj.title_id else None
    if obj.status!='ACTIVE' or obj.revision!=revision or (title and title.revision!=title_revision):
        raise ValidationError('A despesa ou o pagamento mudou. Reabra a edição antes de salvar.')
    if not reason.strip() or len(reason)>500:raise ValidationError('Informe o motivo da edição (até 500 caracteres).')
    allowed={'description','amount','document_date','competence','supplier','counterparty','category','cost_center','notes','recurrence_enabled','due_date','account'}
    if set(data)!=allowed:raise ValidationError('Informe todos os campos da despesa.')
    data={**data,'amount':number(data['amount'],CENT)}
    cutoff=Company.objects.get(pk=1).cutover_date
    if min(data['competence'],data['document_date'])<cutoff:raise ValidationError('Competência e documento devem respeitar o corte da empresa.')
    if data.get('supplier') and not data['supplier'].active and data['supplier'].pk!=obj.supplier_id:
        raise ValidationError('Fornecedor inativo.')
    before=edit_snapshot(obj,title)
    # Preserve historical classification if the same category is retained.
    if (data['category'].pk if data['category'] else None)!=obj.category_id:
        obj.category,obj.category_snapshot,obj.classification,obj.rule_snapshot=classify(data)
    if (obj.category_snapshot.get('nature')=='DEPRECIATION') != (title is None):
        raise ValidationError('Para converter entre despesa financeira e depreciação sem pagamento, cancele e registre na natureza correta.')
    if title:
        if title.status!='OPEN':raise ValidationError('Obrigação financeira cancelada.')
        if data['amount']<title.settled:raise ValidationError('Valor menor que o principal já liquidado. Estorne o pagamento incorreto antes de reduzir.')
        if data['due_date']<data['document_date']:raise ValidationError('Vencimento anterior ao documento.')
        if title.operations.filter(kind='SETTLEMENT',reversal__isnull=True,date__lt=data['document_date']).exists():
            raise ValidationError('Documento não pode ficar após um pagamento existente. Confira a data ou estorne o pagamento incorreto.')
        if data['account'] and data['account'].pk!=title.account_id:account_for(data['account'].pk,data['due_date'])
        elif data['account'] and data['due_date']!=title.due_date:account_for(data['account'].pk,data['due_date'],active=False)
        title.amount=data['amount'];title.description=data['description']
        title.counterparty=data['counterparty'] or str(data['supplier'] or '')
        title.date=data['document_date'];title.due_date=data['due_date'];title.account=data['account'];title.revision+=1
        title.full_clean()
    elif data['recurrence_enabled']:
        raise ValidationError('Depreciação/amortização não admite recorrência financeira.')
    for field in allowed-{'due_date','account','category'}:setattr(obj,field,data[field])
    obj.revision+=1;obj.full_clean(exclude=['cancelled_at'])
    after=edit_snapshot(obj,title)
    entry=ExpenseRevision.objects.create(expense=obj,number=obj.revision,actor=actor,reason=reason.strip(),before=before,after=after)
    if connection.vendor=='postgresql':
        with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.expense_edit', %s, true)",[str(entry.pk)])
    try:
        with transaction.atomic():
            if title:title.save(update_fields=TITLE_FIELDS)
            obj.save(update_fields=EXPENSE_FIELDS)
    finally:
        if connection.vendor=='postgresql':
            with connection.cursor() as cursor:cursor.execute("SELECT set_config('mvet.expense_edit', '', true)")
    audit(actor,obj,'edit_expense',before,{**after,'reason':reason.strip()})
    return obj
