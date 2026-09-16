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
