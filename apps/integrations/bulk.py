"""Signed, revision-bound bulk review. Never confirms sales or purchases."""
from django import forms
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.core.services import require, audit
from apps.inventory.services import domain_lock
from apps.inventory.models import StockLocation
from apps.sales.models import SalesChannel
from apps.expenses.models import ChartOfAccount
from .models import InvoiceImport, PurchaseInvoiceImport

SALT='bling-bulk-review-v1'
LIMIT=5000


def filtered_rows(kind, params):
    if kind=='SALE':
        rows=InvoiceImport.objects.select_related('sale')
        state=params.get('status','PENDING')
        if state in dict(InvoiceImport._meta.get_field('status').choices):rows=rows.filter(status=state)
        if params.get('divergence')=='1':rows=rows.filter(discrepancy=True)
    else:
        rows=PurchaseInvoiceImport.objects.select_related('purchase')
        state=params.get('status','pending')
        if state=='pending':rows=rows.filter(purchase__isnull=True,rejected=False)
        elif state=='rejected':rows=rows.filter(rejected=True)
        elif state=='imported':rows=rows.filter(purchase__isnull=False)
    if params.get('q'):rows=rows.filter(number__icontains=params['q'][:30])
    return rows


def editable(rows,kind):return rows.filter(**{('sale__isnull' if kind=='SALE' else 'purchase__isnull'):True})


def token(actor,kind,pairs):return signing.dumps({'actor':actor.pk,'kind':kind,'rows':pairs},salt=SALT,compress=True)


def decode(actor,kind,value):
    try:data=signing.loads(value,salt=SALT,max_age=3600)
    except signing.BadSignature:raise ValidationError('Seleção expirada ou inválida. Atualize a lista.')
    if data.get('actor')!=actor.pk or data.get('kind')!=kind or not 1<=len(data.get('rows',[]))<=LIMIT:
        raise ValidationError('Seleção inválida ou acima de 5.000 notas; reduza o filtro.')
    return data['rows']


def context(actor,kind,rows,page):
    pending=editable(rows,kind)
    pairs=list(pending.values_list('pk','revision')[:LIMIT+1])
    for obj in page:
        obj.selection_token=token(actor,kind,[(obj.pk,obj.revision)]) if not getattr(obj,'sale_id' if kind=='SALE' else 'purchase_id') else ''
    return dict(bulk_count=len(pairs),bulk_all=token(actor,kind,pairs) if 0<len(pairs)<=LIMIT else '',bulk_kind=kind)


class BulkForm(forms.Form):
    action=forms.ChoiceField(label='Ação',choices=[('ignore','Ignorar / rejeitar'),('reopen','Reabrir'),('edit','Modificar preenchimento')])
    reason=forms.CharField(label='Motivo',max_length=500,initial='Organização das notas a conferir')
    location=forms.ModelChoiceField(label='Estoque',required=False,queryset=StockLocation.objects.filter(active=True))
    channel=forms.ModelChoiceField(label='Canal',required=False,queryset=SalesChannel.objects.filter(active=True))
    acquisition_kind=forms.ChoiceField(label='Tipo de entrada',required=False,choices=[('','Manter'),('NORMAL','Compra com financeiro'),('BONUS','Bonificação sem financeiro')])
    item_mode=forms.ChoiceField(label='Destino de todos os itens',required=False,choices=[('','Manter'),('STOCK','Movimentar estoque'),('NONSTOCK','Somente financeiro — sem estoque')])
    category=forms.ModelChoiceField(label='Categoria sem estoque',required=False,queryset=ChartOfAccount.objects.filter(active=True,postable=True).exclude(nature='REVENUE'))

    def __init__(self,*args,kind,**kwargs):
        super().__init__(*args,**kwargs);self.kind=kind
        for field in (('acquisition_kind','item_mode','category') if kind=='SALE' else ('channel',)):self.fields.pop(field)

    def clean(self):
        data=super().clean()
        if data.get('action')=='edit':
            if not any(data.get(k) for k in self.fields if k not in ('action','reason')):raise forms.ValidationError('Escolha pelo menos um campo para modificar.')
            if data.get('category') and data.get('item_mode')!='NONSTOCK':raise forms.ValidationError('Para aplicar categoria, escolha Somente financeiro.')
            if data.get('acquisition_kind')=='BONUS' and data.get('item_mode')=='NONSTOCK':raise forms.ValidationError('Bonificação é destinada ao estoque.')
        return data

    def changes(self):
        return {k:(v.pk if hasattr(v,'pk') else v) for k,v in self.cleaned_data.items() if k not in ('action','reason') and v}


@transaction.atomic
def apply(*,actor,kind,selection,action,reason,changes):
    require(actor,'core.review_bling' if kind=='SALE' else 'core.operate_purchases')
    if kind=='SALE':require(actor,'core.approve_bling')
    if action not in ('ignore','reopen','edit') or not reason.strip():raise ValidationError('Ação ou motivo inválido.')
    # Validate even service callers; reject arbitrary JSON keys or inactive choices.
    checked=BulkForm(dict(changes,action=action,reason=reason),kind=kind)
    if set(changes)-set(checked.fields) or {'action','reason'} & set(changes):raise ValidationError('Campo não permitido na edição em massa.')
    if not checked.is_valid():raise ValidationError('Campos da edição inválidos. Reabra a prévia.')
    changes=checked.changes() if action=='edit' else {}
    if changes.get('item_mode')=='NONSTOCK' or changes.get('category'):require(actor,'core.operate_expenses')
    domain_lock();pairs=decode(actor,kind,selection)
    expected=dict(pairs)
    if len(expected)!=len(pairs):raise ValidationError('Seleção duplicada.')
    model=InvoiceImport if kind=='SALE' else PurchaseInvoiceImport
    rows=list(model.objects.select_for_update().filter(pk__in=expected).order_by('pk'))
    if len(rows)!=len(expected):raise ValidationError('Uma nota não existe mais. Atualize a lista.')
    for obj in rows:
        if obj.revision!=expected[obj.pk] or getattr(obj,'sale_id' if kind=='SALE' else 'purchase_id'):
            raise ValidationError('Uma nota mudou ou já foi importada. Nenhuma alteração aplicada; atualize a seleção.')
    for obj in rows:
        before={'overrides':obj.review_overrides,'state':obj.status if kind=='SALE' else obj.rejected}
        if action=='edit':obj.review_overrides={**obj.review_overrides,**changes}
        elif kind=='SALE':obj.status='IGNORED' if action=='ignore' else ('ERROR' if obj.error else 'PENDING')
        else:obj.rejected=action=='ignore'
        obj.revision+=1;obj.save()
        audit(actor,obj,'bling_bulk_'+action,before,{'reason':reason,'overrides':obj.review_overrides,'state':obj.status if kind=='SALE' else obj.rejected})
    return len(rows)
