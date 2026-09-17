import uuid
from decimal import Decimal
from django import forms
from django.utils import timezone
from apps.core.models import Company
from apps.products.models import Product
from apps.inventory.models import StockLocation
from .models import Purchase, Supplier
from .services import FIELDS

class SupplierForm(forms.ModelForm):
    class Meta:
        model=Supplier
        fields=['legal_name','trade_name','document','contact','phone','email','notes','active']
        widgets={'notes':forms.Textarea(attrs={'rows':2})}

class PurchaseForm(forms.ModelForm):
    key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    revision=forms.IntegerField(widget=forms.HiddenInput,initial=0)
    class Meta:
        model=Purchase
        fields=FIELDS
        widgets={'date':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'),'notes':forms.Textarea(attrs={'rows':2})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['supplier'].queryset=Supplier.objects.filter(active=True)
        self.fields['location'].queryset=StockLocation.objects.filter(active=True)
        self.fields['date'].initial=timezone.localdate
        if self.instance.pk:
            self.initial['key']=self.instance.key;self.initial['revision']=self.instance.revision
        else:
            company=Company.objects.filter(pk=1).first()
            if company and company.default_stock_location_id and company.default_stock_location.active:self.initial['location']=company.default_stock_location_id
        for field in ['discount','freight','other_costs']:self.fields[field].required=False
    def clean(self):
        data=super().clean()
        for field in ['discount','freight','other_costs']:
            if data.get(field) is None and field not in self.errors:data[field]=Decimal('0')
        return data

class ItemForm(forms.Form):
    product=forms.ModelChoiceField(queryset=Product.objects.filter(active=True,kind='SIMPLE'),widget=forms.HiddenInput(attrs={'data-product-lookup':'true'}),label='Produto')
    quantity=forms.DecimalField(label='Quantidade',max_digits=18,decimal_places=4,min_value=Decimal('0.0001'),initial=1)
    unit_cost=forms.DecimalField(label='Preço unitário (R$)',max_digits=24,decimal_places=6,min_value=0)

Items=forms.formset_factory(ItemForm,extra=1,can_delete=True,max_num=100,validate_max=True)

class InstallmentForm(forms.Form):
    due_date=forms.DateField(label='Vencimento',widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    amount=forms.DecimalField(label='Valor da parcela (R$)',max_digits=18,decimal_places=2,min_value=Decimal('0.01'))
    notes=forms.CharField(label='Observação da parcela',max_length=500,required=False)

Installments=forms.formset_factory(InstallmentForm,extra=0,can_delete=True,max_num=120,validate_max=True)

class ReceiveForm(forms.Form):
    date=forms.DateField(label='Data do recebimento',initial=timezone.localdate,widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    revision=forms.IntegerField(widget=forms.HiddenInput)

class CancelForm(forms.Form):
    reason=forms.CharField(label='Motivo do cancelamento',max_length=500)

class FilterForm(forms.Form):
    q=forms.CharField(label='Documento, SKU ou produto',required=False)
    supplier=forms.ModelChoiceField(label='Fornecedor',queryset=Supplier.objects.all(),required=False)
    location=forms.ModelChoiceField(label='Estoque',queryset=StockLocation.objects.all(),required=False)
    status=forms.ChoiceField(label='Situação da compra',choices=[('','Todas'),*Purchase._meta.get_field('status').choices],required=False)
    start=forms.DateField(label='Compra de',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    end=forms.DateField(label='Compra até',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    due_start=forms.DateField(label='Vencimento de',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    due_end=forms.DateField(label='Vencimento até',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    pending=forms.ChoiceField(label='Parcelas',required=False,choices=[('','Todas'),('pending','Pendentes'),('overdue','Vencidas'),('paid','Pagas')])
    period=forms.ChoiceField(label='Período da compra',required=False,choices=[('','Personalizado'),('today','Hoje'),('yesterday','Ontem'),('week','Semana'),('month','Mês'),('previous_month','Mês anterior'),('year','Ano')])
    sort=forms.ChoiceField(label='Ordenação',required=False,choices=[('-date','Mais recentes'),('date','Mais antigas'),('document','Documento')])
