import uuid
from decimal import Decimal
from django import forms
from django.utils import timezone
from apps.products.models import Product, Brand, ProductCategory
from .models import StockLocation

class ProductForm(forms.ModelForm):
    class Meta:
        model=Product
        fields=['sku','name','unit','kind','brand','category','minimum','active']

class NamedForm(forms.Form):
    name=forms.CharField(label='Nome',max_length=120)
    active=forms.BooleanField(label='Ativo',required=False,initial=True)

class OperationForm(forms.Form):
    key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    kind=forms.ChoiceField(label='Operação',choices=[('RECEIPT','Entrada'),('ISSUE','Saída'),('OPENING','Saldo inicial'),('ADJUST_IN','Ajuste: acréscimo'),('ADJUST_OUT','Ajuste: redução'),('TRANSFER','Transferência'),('SPLIT','Fracionamento'),('KIT_ISSUE','Saída de kit'),('REVALUE','Correção de custo')])
    date=forms.DateField(label='Data',initial=timezone.localdate,widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    product=forms.ModelChoiceField(label='Produto',queryset=Product.objects.filter(active=True),widget=forms.HiddenInput(attrs={'data-product-lookup':'true'}))
    location=forms.ModelChoiceField(label='Local de origem',queryset=StockLocation.objects.filter(active=True))
    quantity=forms.DecimalField(label='Quantidade',max_digits=18,decimal_places=4,min_value=0,initial=1)
    cost=forms.DecimalField(label='Custo unitário (R$)',max_digits=24,decimal_places=6,min_value=0,required=False,help_text='Obrigatório na abertura, entrada, acréscimo ou correção de custo. Zero deve ser informado explicitamente.')
    target_location=forms.ModelChoiceField(label='Local de destino',queryset=StockLocation.objects.filter(active=True),required=False)
    target_product=forms.ModelChoiceField(label='Produto de destino',queryset=Product.objects.filter(active=True,kind='SIMPLE'),required=False,widget=forms.HiddenInput(attrs={'data-product-lookup':'true'}))
    target_quantity=forms.DecimalField(label='Quantidade produzida',max_digits=18,decimal_places=4,min_value=0,required=False)
    reason=forms.CharField(label='Motivo / documento',max_length=500,widget=forms.Textarea(attrs={'rows':2}))
    def __init__(self,*args,actor,**kwargs):
        super().__init__(*args,**kwargs)
        actions={'TRANSFER':'transfer_stock','SPLIT':'fraction_stock','REVALUE':'adjust_stock_cost','OPENING':'receive_stock','RECEIPT':'receive_stock'}
        self.fields['kind'].choices=[x for x in self.fields['kind'].choices if actor.has_perm('core.'+actions.get(x[0],'adjust_stock'))]
        if not actor.has_perm('core.view_costs'):
            self.fields['kind'].choices=[x for x in self.fields['kind'].choices if x[0] not in {'OPENING','RECEIPT','ADJUST_IN','REVALUE'}]
            self.fields.pop('cost')
    def clean(self):
        data=super().clean();kind=data.get('kind')
        for field,needed in [('cost',kind in {'OPENING','RECEIPT','ADJUST_IN','REVALUE'}),('target_location',kind=='TRANSFER'),('target_product',kind=='SPLIT'),('target_quantity',kind=='SPLIT')]:
            if needed and data.get(field) is None:self.add_error(field,'Campo obrigatório para esta operação.')
        if kind=='REVALUE':data['quantity']=0
        return data

class ReversalForm(forms.Form):
    key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    date=forms.DateField(label='Data',initial=timezone.localdate,widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    reason=forms.CharField(label='Motivo do estorno',max_length=500)

class ComponentForm(forms.Form):
    component=forms.ModelChoiceField(label='Componente',queryset=Product.objects.filter(active=True,kind='SIMPLE'),widget=forms.HiddenInput(attrs={'data-product-lookup':'true'}))
    quantity=forms.DecimalField(label='Quantidade por kit',max_digits=18,decimal_places=4,min_value=Decimal("0.0001"))
Components=forms.formset_factory(ComponentForm,extra=1,can_delete=True,max_num=100,validate_max=True)


class CountForm(forms.Form):
    snapshot = forms.CharField(widget=forms.HiddenInput)
    counted = forms.DecimalField(label='Quantidade contada', min_value=0, max_digits=18, decimal_places=4)
    reason = forms.CharField(label='Motivo / observação da contagem', max_length=350, widget=forms.Textarea(attrs={'rows':3}))


class InventoryUploadForm(forms.Form):
    file = forms.FileField(label='Planilha Excel (.xlsx)', widget=forms.ClearableFileInput(attrs={'accept':'.xlsx,.json'}))
    mode = forms.ChoiceField(label='Como aplicar', required=False, initial='current', choices=[('current','Substituir a posição atual'),('historical','Posição de uma data passada')])
    base_date = forms.DateField(label='Data-base (somente posição passada)', required=False,
        widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    location = forms.ModelChoiceField(label='Depósito', queryset=StockLocation.objects.filter(active=True), required=False,
        empty_label='Usar a coluna Depósito da planilha')
    complete = forms.BooleanField(label='Zerar SKUs ausentes nos depósitos da planilha', required=False,
        help_text='Desmarcado: altera somente os produtos enviados. Marque apenas para uma contagem completa.')

    def clean(self):
        data = super().clean()
        data['mode'] = data.get('mode') or 'current'
        file = data.get('file')
        if file and file.name.lower().endswith('.xlsx') and data['mode'] == 'historical':
            if not data.get('base_date'):
                self.add_error('base_date','Informe a data-base.')
            elif data['base_date'] > timezone.localdate():
                self.add_error('base_date','A data-base não pode ser futura.')
        return data


class TransferBatchForm(forms.Form):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    date = forms.DateField(label='Data', initial=timezone.localdate, widget=forms.DateInput(attrs={'type':'date'}, format='%Y-%m-%d'))
    location = forms.ModelChoiceField(label='Local de origem', queryset=StockLocation.objects.filter(active=True))
    target_location = forms.ModelChoiceField(label='Local de destino', queryset=StockLocation.objects.filter(active=True))
    reason = forms.CharField(label='Motivo / documento do envio', max_length=500, widget=forms.Textarea(attrs={'rows':2}))


class TransferItemForm(forms.Form):
    product = forms.ModelChoiceField(label='Produto', queryset=Product.objects.filter(active=True,kind='SIMPLE'), widget=forms.HiddenInput(attrs={'data-product-lookup':'true'}))
    quantity = forms.DecimalField(label='Quantidade a transferir', max_digits=18, decimal_places=4, min_value=Decimal('0.0001'))


TransferItems = forms.formset_factory(TransferItemForm, extra=1, can_delete=True, min_num=1, validate_min=True, max_num=200, validate_max=True, absolute_max=200)
