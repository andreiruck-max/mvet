"""Accrual expenses and classification; payments stay in the cash ledger."""
import calendar
import re
from decimal import Decimal
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.core.models import Company
from apps.core.services import require, audit
from apps.inventory.services import domain_lock, number, _fingerprint
from apps.finance.models import FinancialTitle
from apps.finance.services import account_for, repeat, cancel_origin
from .models import ChartOfAccount as Category, ClassificationRule as Rule, Expense, ExpenseRevision

CENT=Decimal('0.01')
EXPENSE_NATURES={'OPERATING','FINANCIAL'}


def category_path(category, *, expense=True):
    path=[];seen=set()
    node=Category.objects.get(pk=category.pk)
    leaf=node
    while node:
        if node.pk in seen or len(path)>=8: raise ValidationError('Hierarquia inválida ou acima de oito níveis.')
        if not node.active: raise ValidationError('Categoria ou ancestral inativo.')
        seen.add(node.pk);path.append({'id':node.pk,'code':node.code,'name':node.name,'nature':node.nature})
        node=node.parent
    if expense and (not leaf.postable or leaf.nature not in EXPENSE_NATURES):
        raise ValidationError('Escolha categoria analítica de despesa operacional ou financeira.')
    return {'path':list(reversed(path)),'nature':leaf.nature}


@transaction.atomic
def save_category(*,actor,data,pk=None):
    require(actor,'core.manage_expense_rules');domain_lock()
    obj=Category.objects.select_for_update().get(pk=pk) if pk else Category()
    allowed={'code','name','parent','nature','postable','active'}
    if set(data)-allowed: raise ValidationError('Campo de categoria inválido.')
    before={k:str(getattr(obj,k)) for k in allowed}
    for k,v in data.items():setattr(obj,k,v)
    if not re.fullmatch(r'[0-9]{2}(\.[0-9]{2}){0,7}',obj.code): raise ValidationError('Use códigos com dois dígitos por nível, como 04.01, até oito níveis.')
    if obj.parent:
        if obj.parent_id==obj.pk: raise ValidationError('Categoria não pode ser superior a si mesma.')
        path=category_path(obj.parent,expense=False)
        if any(n['id']==obj.pk for n in path['path']):raise ValidationError('Ciclo na hierarquia.')
        if obj.parent.postable or obj.nature!=obj.parent.nature:raise ValidationError('Categoria superior deve ser agrupadora e possuir a mesma natureza.')
        if obj.code.rsplit('.',1)[0]!=obj.parent.code or '.' not in obj.code:raise ValidationError('Código deve ser filho direto do código superior.')
    elif '.' in obj.code:raise ValidationError('Código com subnível exige categoria superior.')
    if pk and (obj.children.exists() or obj.expenses.exists() or Rule.objects.filter(category=obj).exists()):
        for field in ['code','parent','nature','postable']:
            if str(getattr(obj,field))!=before[field]:raise ValidationError('Estrutura utilizada é histórica; crie outra categoria. Nome e atividade podem ser ajustados.')
    obj.full_clean();obj.save()
    audit(actor,obj,'save_chart_account',before,{k:str(getattr(obj,k)) for k in allowed});return obj


@transaction.atomic
def save_rule(*,actor,data,pk=None):
    require(actor,'core.manage_expense_rules');domain_lock()
    obj=Rule.objects.select_for_update().get(pk=pk) if pk else Rule()
    allowed={'name','priority','field','operator','value','category','active'}
    if set(data)-allowed:raise ValidationError('Campo de regra inválido.')
    before={k:str(getattr(obj,k)) for k in allowed} if pk else {}
    for k,v in data.items():setattr(obj,k,v)
    obj.value=obj.value.strip()
    if not obj.value:raise ValidationError('Regra exige um valor não vazio.')
    if obj.active:category_path(obj.category)
    obj.full_clean();obj.save();audit(actor,obj,'save_classification_rule',before,{k:str(getattr(obj,k)) for k in allowed});return obj


def classify(data):
    if data.get('category'):
        return data['category'],category_path(data['category']),'MANUAL',{}
    values={'description':data['description'],'counterparty':data.get('counterparty',''),'supplier_document':data['supplier'].document if data.get('supplier') else ''}
    for rule in Rule.objects.filter(active=True).select_related('category').order_by('priority','pk'):
        left=values[rule.field].strip().casefold();right=rule.value.strip().casefold()
        matches=(right in left if rule.operator=='CONTAINS' else left==right if rule.operator=='EQUALS' else left.startswith(right))
        if not matches:continue
        try:snapshot=category_path(rule.category)
        except ValidationError:continue
        return rule.category,snapshot,'RULE',{'id':rule.pk,'name':rule.name,'priority':rule.priority,'field':rule.field,'operator':rule.operator,'value':rule.value}
    return None,{},'NONE',{}


def classification_snapshot(expense):
    return {k:getattr(expense,k) for k in ['category_id','category_snapshot','classification','rule_snapshot','cost_center']}


@transaction.atomic
def create_expense(*,actor,key,data,recurrence_of=None,recurrence_index=0):
    require(actor,'core.operate_expenses');domain_lock()
    allowed={'document_date','competence','description','supplier','counterparty','amount','category','cost_center','notes','due_date','account','recurrence_enabled'}
    if set(data)-allowed:raise ValidationError('Campo de despesa inválido.')
    data={**data,'amount':number(data['amount'],CENT)}
    key,fingerprint,existing=repeat(Expense,key,[actor.pk,{k:str(v.pk if hasattr(v,'pk') else v) for k,v in data.items()},recurrence_of.pk if recurrence_of else None,recurrence_index])
    if existing:return existing
    cutoff=Company.objects.get(pk=1).cutover_date
    if data['competence']<cutoff or data['document_date']<cutoff:raise ValidationError('Competência e documento devem respeitar o corte. Pendências anteriores são abertura financeira.')
    if data['due_date']<data['document_date']:raise ValidationError('Vencimento anterior ao documento.')
    if data.get('supplier') and not data['supplier'].active:raise ValidationError('Fornecedor inativo.')
    if data.get('account'):account_for(data['account'].pk,data['due_date'])
    category,snapshot,method,rule=classify(data)
    values={k:v for k,v in data.items() if k not in {'account','due_date','category'}}
    title=FinancialTitle.objects.create(direction='PAY',description=data['description'],counterparty=data.get('counterparty') or str(data.get('supplier') or ''),date=data['document_date'],due_date=data['due_date'],amount=data['amount'],account=data.get('account'),actor=actor,source='expense',category='OTHER')
    obj=Expense(key=key,fingerprint=fingerprint,actor=actor,title=title,category=category,category_snapshot=snapshot,classification=method,rule_snapshot=rule,recurrence_of=recurrence_of,recurrence_index=recurrence_index,**values)
    obj.full_clean(exclude=['cancelled_at']);obj.save()
    audit(actor,obj,'create_expense',{}, {'competence':str(obj.competence),'amount':str(obj.amount),'title':title.pk,**classification_snapshot(obj)})
    return obj


@transaction.atomic
def reclassify(*,actor,pk,category,cost_center,reason,revision,automatic=False):
    require(actor,'core.operate_expenses');domain_lock()
    obj=Expense.objects.select_for_update().get(pk=pk)
    if obj.status!='ACTIVE':raise ValidationError('Despesa cancelada.')
    if obj.revision!=revision:raise ValidationError('Despesa mudou; reabra antes de classificar.')
    if not reason.strip() or len(reason)>500:raise ValidationError('Informe motivo de até 500 caracteres.')
    if len(cost_center)>120:raise ValidationError('Centro de custo excede 120 caracteres.')
    before=classification_snapshot(obj)
    data={'description':obj.description,'counterparty':obj.counterparty,'supplier':obj.supplier,'category':None if automatic else category}
    if not automatic and not category:raise ValidationError('Selecione categoria ou marque Aplicar regras atuais.')
    obj.category,obj.category_snapshot,obj.classification,obj.rule_snapshot=classify(data)
    obj.cost_center=cost_center;obj.revision+=1
    after=classification_snapshot(obj)
    ExpenseRevision.objects.create(expense=obj,number=obj.revision,actor=actor,reason=reason,before=before,after=after)
    obj.save(update_fields=['category','category_snapshot','classification','rule_snapshot','cost_center','revision'])
    audit(actor,obj,'reclassify_expense',before,{**after,'reason':reason});return obj


@transaction.atomic
def cancel_expense(*,actor,pk,reason):
    require(actor,'core.operate_expenses');domain_lock()
    obj=Expense.objects.select_for_update().get(pk=pk)
    if obj.status=='CANCELLED':return obj
    cancel_origin(actor,reason,pk=obj.title_id)
    obj.status='CANCELLED';obj.cancelled_at=timezone.now();obj.cancellation_reason=reason;obj.revision+=1
    obj.save(update_fields=['status','cancelled_at','cancellation_reason','revision'])
    audit(actor,obj,'cancel_expense',{'status':'ACTIVE'},{'reason':reason});return obj


def month_shift(date,offset):
    year,month=divmod(date.year*12+date.month-1+offset,12)
    return date.replace(year=year,month=month+1,day=min(date.day,calendar.monthrange(year,month+1)[1]))


def recurrence_preview(expense,months):
    if not 1<=months<=24:raise ValidationError('Gere de 1 a 24 meses por vez.')
    if expense.recurrence_of_id or not expense.recurrence_enabled or expense.status!='ACTIVE':raise ValidationError('Recorrência deve partir de despesa-base ativa e habilitada.')
    title=expense.title
    existing=set(expense.occurrences.values_list('recurrence_index',flat=True))
    rows=[]
    for i in range(1,months+1):
        data={k:getattr(expense,k) for k in ['document_date','description','supplier','counterparty','amount','category','cost_center','notes']}
        data.update(competence=month_shift(expense.competence,i),due_date=month_shift(title.due_date,i),account=title.account,recurrence_enabled=False)
        # Manual decisions carry forward; automatic decisions use current rules.
        if expense.classification!='MANUAL':data['category']=None
        category,snapshot,method,rule=classify(data)
        rows.append({'index':i,'data':data,'category':str(category) if category else 'A classificar','snapshot':snapshot,'rule':rule,'skip':i in existing})
    payload=[{'index':r['index'],'data':{k:str(v.pk if hasattr(v,'pk') else v) for k,v in r['data'].items()},'snapshot':r['snapshot'],'rule':r['rule']} for r in rows]
    return rows,_fingerprint([expense.pk,expense.revision,title.revision,payload])


@transaction.atomic
def generate_recurrence(*,actor,pk,months,preview_hash):
    require(actor,'core.operate_expenses');domain_lock()
    base=Expense.objects.select_for_update().get(pk=pk)
    rows,current_hash=recurrence_preview(base,months)
    if current_hash!=preview_hash:raise ValidationError('Dados ou regras mudaram. Revise uma nova prévia antes de gerar.')
    created=[]
    for row in rows:
        if row['skip']:continue
        created.append(create_expense(actor=actor,key=uuid4(),data=row['data'],recurrence_of=base,recurrence_index=row['index']))
    audit(actor,base,'generate_monthly_expenses',{}, {'months':months,'created':[e.pk for e in created]})
    return created


@transaction.atomic
def stop_recurrence(*,actor,pk):
    require(actor,'core.operate_expenses');domain_lock()
    obj=Expense.objects.select_for_update().get(pk=pk)
    if obj.status!='ACTIVE':raise ValidationError('Despesa cancelada.')
    if not obj.recurrence_enabled:return obj
    obj.recurrence_enabled=False;obj.revision+=1;obj.save(update_fields=['recurrence_enabled','revision'])
    audit(actor,obj,'stop_expense_recurrence',{}, {'stopped':True});return obj
