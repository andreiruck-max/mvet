"""Cash ledger services; obligations are not bank movements or DRE entries."""
from decimal import Decimal
from uuid import UUID
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.core.models import Company
from apps.core.services import require, audit
from apps.inventory.services import domain_lock, number, _fingerprint
from .models import FinancialAccount as Account, FinancialTitle as Title, FinancialOperation as Operation, FinancialEntry as Entry

CENT = Decimal('0.01')
ZERO = Decimal('0')


def validate_date(date, *, future=False):
    if date < Company.objects.get(pk=1).cutover_date or (not future and date > timezone.localdate()):
        raise ValidationError('Data deve respeitar o corte; valores realizados não podem ter data futura.')


def account_for(pk, date, *, active=True):
    account = Account.objects.select_for_update().get(pk=pk)
    if active and not account.active:
        raise ValidationError('Conta inativa.')
    if date < account.opening_date:
        raise ValidationError('Data anterior ao saldo inicial da conta.')
    return account


def repeat(model, key, payload):
    try:
        key = UUID(str(key))
    except (ValueError, TypeError):
        raise ValidationError('Identificador de envio inválido.')
    fingerprint = _fingerprint(payload)
    existing = model.objects.filter(key=key).first()
    if existing and existing.fingerprint != fingerprint:
        raise ValidationError('Envio já utilizado com dados diferentes.')
    return key, fingerprint, existing


@transaction.atomic
def save_account(*, actor, data, pk=None):
    require(actor,'core.manage_financial_accounts')
    require(actor, 'core.view_finance')
    require(actor, 'core.operate_finance'); domain_lock()
    account = Account.objects.select_for_update().get(pk=pk) if pk else Account()
    allowed = {'name','institution','kind','opening_balance','opening_date','active'}
    if set(data)-allowed: raise ValidationError('Campo de conta inválido.')
    before = {k:str(getattr(account,k)) for k in allowed}
    if pk and (account.entries.exists() or account.financialtitle_set.exists()):
        if any(data.get(k,getattr(account,k)) != getattr(account,k) for k in ['opening_date','opening_balance']):
            raise ValidationError('Conta utilizada: saldo inicial é histórico. Registre um ajuste patrimonial identificado.')
    for field,value in data.items(): setattr(account,field,value)
    number(abs(account.opening_balance),CENT,zero=True)
    validate_date(account.opening_date)
    account.full_clean(); account.save()
    audit(actor,account,'save_financial_account',before,{k:str(getattr(account,k)) for k in allowed})
    return account


@transaction.atomic
def delete_account(*, actor, pk):
    require(actor,'core.manage_financial_accounts')
    require(actor, 'core.view_finance')
    require(actor,'core.operate_finance'); domain_lock()
    account = Account.objects.select_for_update().get(pk=pk)
    if account.entries.exists() or account.financialtitle_set.exists():
        raise ValidationError('Conta possui histórico: somente inativação é permitida.')
    audit(actor,account,'delete_unused_account',{'name':account.name,'opening_balance':str(account.opening_balance)})
    account.delete()


@transaction.atomic
def create_title(*, actor, key, data):
    require(actor,'core.create_financial_titles')
    require(actor,'core.operate_finance'); domain_lock()
    allowed = {'direction','description','counterparty','date','due_date','amount','account','category','opening','notes'}
    if set(data)-allowed: raise ValidationError('Campo de título inválido.')
    data={**data,'amount':number(data['amount'],CENT)}
    key, fingerprint, existing = repeat(Title,key,[actor.pk,{k:str(v.pk if hasattr(v,'pk') else v) for k,v in data.items()}])
    if existing: return existing
    title = Title(key=key,fingerprint=fingerprint,actor=actor,**data)
    number(title.amount,CENT)
    cutoff = Company.objects.get(pk=1).cutover_date
    if title.opening:
        if title.date >= cutoff: raise ValidationError('Pendência de abertura exige origem anterior ao corte.')
        title.category='OPENING'
    else: validate_date(title.date, future=True)
    if title.due_date < title.date: raise ValidationError('Vencimento anterior à origem.')
    if title.account_id: account_for(title.account_id,max(cutoff,title.due_date))
    title.full_clean(); title.save()
    audit(actor,title,'create_financial_title',{}, {'amount':str(title.amount),'direction':title.direction,'opening':title.opening})
    return title


@transaction.atomic
def schedule_title(*, actor, pk, due_date, account, notes, revision):
    require(actor,'core.schedule_financial_titles')
    require(actor,'core.operate_finance'); domain_lock()
    title = Title.objects.select_for_update().get(pk=pk)
    if title.status!='OPEN' or not title.remaining: raise ValidationError('Título encerrado.')
    if title.revision != revision: raise ValidationError('Título mudou; reabra para atualizar.')
    if due_date < title.date: raise ValidationError('Vencimento anterior à origem.')
    if account: account_for(account.pk,max(due_date,Company.objects.get(pk=1).cutover_date))
    before={'due_date':str(title.due_date),'account':title.account_id,'notes':title.notes}
    title.due_date=due_date; title.account=account; title.notes=notes; title.revision+=1
    title.full_clean(); title.save(update_fields=['due_date','account','notes','revision'])
    audit(actor,title,'reschedule_title',before,{'due_date':str(due_date),'account':title.account_id,'notes':notes})
    return title


@transaction.atomic
def settle(*, actor, key, title_id, account_id, date, principal, interest, discount, actual, notes='', revision):
    require(actor,'core.operate_finance'); domain_lock()
    title = Title.objects.select_for_update().get(pk=title_id)
    require(actor, 'core.pay_titles' if title.direction=='PAY' else 'core.receive_titles')
    principal=number(principal,CENT)
    interest,discount,actual=[number(v,CENT,zero=True) for v in [interest,discount,actual]]
    key, fingerprint, existing = repeat(Operation,key,[actor.pk,title_id,account_id,date,principal,interest,discount,actual,notes,revision])
    if existing: return existing
    if title.revision != revision: raise ValidationError('Título já foi atualizado. Reabra antes de liquidar.')
    if title.status!='OPEN' or not title.remaining: raise ValidationError('Título encerrado.')
    validate_date(date)
    if not title.opening and date < title.date: raise ValidationError('Liquidação anterior à origem.')
    number(principal,CENT)
    for value in [interest,discount,actual]: number(value,CENT,zero=True)
    if principal > title.remaining: raise ValidationError('Principal excede o saldo pendente.')
    if discount > principal+interest or actual != principal+interest-discount:
        raise ValidationError('Valor efetivo deve ser principal + juros − desconto. Informe diferenças explicitamente.')
    if (interest or discount) and not notes.strip(): raise ValidationError('Explique juros, descontos ou retenções na observação.')
    account=account_for(account_id,date)
    op=Operation(key=key,fingerprint=fingerprint,kind='SETTLEMENT',date=date,description=notes or title.description,title=title,principal=principal,interest=interest,discount=discount,actual=actual,actor=actor)
    op.full_clean(); op.save()
    if actual: Entry.objects.create(operation=op,account=account,amount=actual if title.direction=='RECEIVE' else -actual)
    before=title.settled; title.settled+=principal; title.revision+=1
    title.save(update_fields=['settled','revision'])
    audit(actor,op,'settle_title',{'settled':str(before)}, {'title':title.pk,'principal':str(principal),'interest':str(interest),'discount':str(discount),'actual':str(actual),'account':account.pk,'date':str(date)})
    return op


@transaction.atomic
def transfer(*, actor, key, source_id, destination_id, date, amount, notes='', planned=False):
    require(actor,'core.transfer_finance')
    require(actor,'core.operate_finance'); domain_lock()
    amount=number(amount,CENT)
    key,fingerprint,existing=repeat(Operation,key,[actor.pk,source_id,destination_id,date,amount,notes,planned])
    if existing: return existing
    if source_id==destination_id: raise ValidationError('Escolha duas contas diferentes.')
    number(amount,CENT); validate_date(date,future=planned)
    accounts={pk:account_for(pk,date) for pk in sorted([source_id,destination_id])}
    op=Operation(key=key,fingerprint=fingerprint,kind='TRANSFER',status='PLANNED' if planned else 'POSTED',date=date,actual=amount,description=notes or 'Transferência entre contas',actor=actor)
    op.full_clean(); op.save()
    Entry.objects.create(operation=op,account=accounts[source_id],amount=-amount)
    Entry.objects.create(operation=op,account=accounts[destination_id],amount=amount)
    audit(actor,op,'transfer_accounts',{}, {'source':source_id,'destination':destination_id,'amount':str(amount),'date':str(date),'status':op.status})
    return op


@transaction.atomic
def post_transfer(*, actor, pk, date):
    require(actor,'core.transfer_finance')
    require(actor,'core.operate_finance'); domain_lock()
    op=Operation.objects.select_for_update().get(pk=pk)
    if op.status=='POSTED': return op
    if op.kind!='TRANSFER' or op.status!='PLANNED': raise ValidationError('Transferência não está prevista.')
    validate_date(date)
    for entry in op.entries.order_by('account_id'): account_for(entry.account_id,date)
    before={'date':str(op.date),'status':op.status}
    op.date=date; op.status='POSTED'; op.save(update_fields=['date','status'])
    audit(actor,op,'post_transfer',before,{'date':str(date),'status':op.status})
    return op


@transaction.atomic
def reverse(*, actor, pk, date, reason):
    require(actor,'core.reverse_finance')
    require(actor,'core.operate_finance'); domain_lock()
    if not reason.strip() or len(reason)>500: raise ValidationError('Informe motivo de até 500 caracteres.')
    op=Operation.objects.select_for_update().get(pk=pk)
    if op.kind=='REVERSAL': raise ValidationError('Não estorne um estorno; registre nova operação.')
    if hasattr(op,'reversal'): return op.reversal
    if op.status=='CANCELLED': return op
    if op.status=='PLANNED':
        op.status='CANCELLED'; op.save(update_fields=['status'])
        audit(actor,op,'cancel_planned_transfer',{}, {'reason':reason}); return op
    validate_date(date)
    if date < op.date: raise ValidationError('Estorno não pode preceder a operação original.')
    reversal=Operation.objects.create(kind='REVERSAL',date=date,description=reason,actor=actor,reversal_of=op,fingerprint=_fingerprint(['reverse',op.pk]),actual=op.actual)
    for entry in op.entries.order_by('account_id'):
        account_for(entry.account_id,date,active=False)
        Entry.objects.create(operation=reversal,account_id=entry.account_id,amount=-entry.amount)
    if op.title_id:
        title=Title.objects.select_for_update().get(pk=op.title_id)
        title.settled-=op.principal; title.revision+=1; title.save(update_fields=['settled','revision'])
    audit(actor,reversal,'reverse_financial_operation',{'operation':op.pk},{'reason':reason,'date':str(date)})
    return reversal


@transaction.atomic
def cancel_title(*, actor, pk, reason):
    require(actor,'core.cancel_financial_titles')
    require(actor,'core.operate_finance'); domain_lock()
    title=Title.objects.select_for_update().get(pk=pk)
    if title.purchase_installment_id or title.sale_id or hasattr(title,'expense'): raise ValidationError('Cancele pela compra, venda ou despesa de origem, após estornar liquidações.')
    _cancel_titles(actor,Title.objects.filter(pk=pk),reason)


def _cancel_titles(actor, rows, reason):
    """Internal hook: caller holds shared domain lock and its own permission."""
    if not reason.strip() or len(reason)>500: raise ValidationError('Informe motivo de até 500 caracteres.')
    titles=list(rows.select_for_update())
    if any(t.settled for t in titles): raise ValidationError('Há liquidações: estorne pagamentos/recebimentos antes de cancelar a origem.')
    for title in titles:
        if title.status=='CANCELLED': continue
        title.status='CANCELLED'; title.revision+=1; title.save(update_fields=['status','revision'])
        audit(actor,title,'cancel_title',{}, {'reason':reason})


def create_purchase_titles(purchase, actor):
    for installment in purchase.installments.all():
        Title.objects.get_or_create(purchase_installment=installment,defaults=dict(direction='PAY',description=f'Compra {purchase.document} · parcela {installment.number}',counterparty=str(purchase.supplier),date=purchase.date,due_date=installment.due_date,amount=installment.amount,actor=actor,source='purchase',category='PRINCIPAL'))


def create_sale_title(sale, actor):
    if sale.revenue>0:
        Title.objects.get_or_create(sale=sale,defaults=dict(direction='RECEIVE',description=f'Venda NF {sale.invoice_number}/{sale.invoice_series}',date=sale.date,due_date=sale.date,amount=sale.revenue,actor=actor,source='sale',category='OPERATING'))


def cancel_origin(actor, reason, **filters):
    _cancel_titles(actor,Title.objects.filter(**filters),reason)
