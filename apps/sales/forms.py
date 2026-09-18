import uuid
from decimal import Decimal
from django import forms
from django.utils import timezone
from apps.products.models import Product
from apps.core.models import Company
from apps.inventory.models import StockLocation
from .models import Sale, SalesChannel, TaxRule
from .services import EDIT_FIELDS, FINANCIAL_FIELDS

class SaleForm(forms.ModelForm):
    key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    revision=forms.IntegerField(widget=forms.HiddenInput,initial=0)
    revenue_target=forms.DecimalField(label='Receita líquida operacional ajustada (R$)', required=False, max_digits=18, decimal_places=2, min_value=0,
        help_text='Master: valor antes de CMV, impostos e custos variáveis. Não é o saldo recebido do marketplace. Regra tributária sobre receita inclui este ajuste na base.')
    class Meta:
        model=Sale
        fields=EDIT_FIELDS
        widgets={'date':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'),'notes':forms.Textarea(attrs={'rows':2})}
    def __init__(self,*args,actor=None,**kwargs):
        self.actor=actor
        super().__init__(*args,**kwargs)
        self.fields['revenue_adjustment'].widget=forms.HiddenInput()
        self.fields['revenue_adjustment'].disabled=True
        self.master_fields=[]
        if actor and actor.is_superuser:
            for name in EDIT_FIELDS:self.fields[name].required=False
            self.master_fields=[self['revenue_target'],self['revenue_adjustment_reason']]
            if self.instance.pk and self.instance.revenue_adjustment:self.initial['revenue_target']=self.instance.revenue
        else:
            self.fields.pop('revenue_target')
            self.fields['revenue_adjustment_reason'].widget=forms.HiddenInput()
            self.fields['revenue_adjustment_reason'].disabled=True
            self.fields['channel'].required=True
            self.fields['location'].required=True
        self.fields['date'].initial=timezone.localdate
        self.fields['channel'].queryset=SalesChannel.objects.filter(active=True)
        self.fields['location'].queryset=StockLocation.objects.filter(active=True)
        self.fields['tax_rule'].queryset=TaxRule.objects.filter(active=True)
        for name in ['channel','tax_rule']:
            if self.fields[name].queryset.count()==1:self.fields[name].initial=self.fields[name].queryset.first()
        company=Company.objects.select_related('default_stock_location').filter(pk=1).first()
        if not self.instance.pk and company and company.default_stock_location and company.default_stock_location.active:
            self.initial['location']=company.default_stock_location_id
        elif not self.instance.pk and company and not company.default_stock_location_id and self.fields['location'].queryset.count()==1:
            self.initial['location']=self.fields['location'].queryset.first().pk
        self.fields['location'].label='Estoque da venda'
        self.basic_fields=[self[name] for name in ['date','invoice_number','invoice_series','channel','location','products_amount','tax_rule']]
        self.optional_fields=[self[name] for name in [*FINANCIAL_FIELDS[1:],'tax_override','tax_reason','notes']]
        for name in FINANCIAL_FIELDS[1:]:self.fields[name].required=False
        if self.instance.pk:
            self.fields['key'].initial=self.instance.key
            self.fields['revision'].initial=self.instance.revision

    def clean(self):
        data=super().clean()
        for name in FINANCIAL_FIELDS[1:]:
            if data.get(name) is None and name not in self.errors:data[name]=Decimal('0')
        if self.actor and self.actor.is_superuser:
            data['date']=data.get('date') or timezone.localdate()
            if data.get('products_amount') is None and 'products_amount' not in self.errors:data['products_amount']=Decimal('0')
            if data.get('tax_override') is None and not data.get('tax_rule'):data['tax_override']=Decimal('0')
            if data.get('tax_override') is not None and not data.get('tax_reason'):data['tax_reason']='Imposto manual definido pelo master.'
            if data.get('revenue_target') is not None and all(data.get(f) is not None for f in ['products_amount','discount','shipping_received']):
                data['revenue_adjustment']=data['revenue_target']-(data['products_amount']-data['discount']+data['shipping_received'])
                if data['revenue_adjustment'] and not data.get('revenue_adjustment_reason'):data['revenue_adjustment_reason']='Ajuste gerencial definido pelo master.'
        return data

class ItemForm(forms.Form):
    product=forms.ModelChoiceField(label='Produto',queryset=Product.objects.filter(active=True),widget=forms.HiddenInput(attrs={'data-product-lookup':'true'}))
    quantity=forms.DecimalField(label='Quantidade',max_digits=18,decimal_places=4,min_value=Decimal('0.0001'),initial=1)

Items=forms.formset_factory(ItemForm,extra=1,can_delete=True,max_num=100,validate_max=True)

class MasterItemForm(ItemForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['product'].required=False
        self.fields['quantity'].required=False
    def clean(self):
        data=super().clean()
        if data.get('product') and data.get('quantity') is None and 'quantity' not in self.errors:data['quantity']=Decimal('1')
        return data

MasterItems=forms.formset_factory(MasterItemForm,extra=1,can_delete=True,max_num=100,validate_max=True)

class CancelForm(forms.Form):
    reason=forms.CharField(label='Motivo do cancelamento',max_length=500)

class ChannelForm(forms.ModelForm):
    class Meta:
        model=SalesChannel
        fields=['name','active']

class TaxForm(forms.ModelForm):
    class Meta:
        model=TaxRule
        fields=['name','rate','starts_on','ends_on','base','active']
        widgets={field:forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d') for field in ['starts_on','ends_on']}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance.pk:
            for field in ['rate','starts_on','base']:self.fields[field].disabled=True

class TaxChangeForm(forms.Form):
    rate=forms.DecimalField(label='Nova alíquota (%)',max_digits=7,decimal_places=4,min_value=0,max_value=100)
    effective_from=forms.DateField(label='Usar a partir de',initial=timezone.localdate,widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    base=forms.ChoiceField(label='Base de cálculo',choices=TaxRule._meta.get_field('base').choices)
    reason=forms.CharField(label='Motivo da alteração',max_length=500)
    revision=forms.IntegerField(widget=forms.HiddenInput,initial=0)

class ExtraCostForm(forms.Form):
    name=forms.CharField(label='Taxa / descrição',max_length=120)
    amount=forms.DecimalField(label='Valor (R$)',max_digits=18,decimal_places=2,min_value=0)

ExtraCosts=forms.formset_factory(ExtraCostForm,extra=0,can_delete=True,max_num=100,validate_max=True)

class MasterExtraCostForm(ExtraCostForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for field in self.fields.values():field.required=False
    def clean(self):
        data=super().clean()
        if data.get('name') or data.get('amount') is not None:
            data['name']=data.get('name') or 'Taxa extra definida pelo master'
            if data.get('amount') is None and 'amount' not in self.errors:data['amount']=Decimal('0')
        return data

MasterExtraCosts=forms.formset_factory(MasterExtraCostForm,extra=0,can_delete=True,max_num=100,validate_max=True)

class FilterForm(forms.Form):
    q=forms.CharField(label='NF ou produto',required=False)
    start=forms.DateField(label='De',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    end=forms.DateField(label='Até',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    channel=forms.ModelChoiceField(label='Canal',queryset=SalesChannel.objects.all(),required=False)
    location=forms.ModelChoiceField(label='Estoque',queryset=StockLocation.objects.all(),required=False)
    status=forms.ChoiceField(label='Status',choices=[('','Todos'),*Sale._meta.get_field('status').choices],required=False)
    period=forms.ChoiceField(label='Período',required=False,choices=[('','Personalizado'),('today','Hoje'),('yesterday','Ontem'),('week','Semana'),('month','Mês'),('previous_month','Mês anterior'),('year','Ano')])
    sort=forms.ChoiceField(label='Ordenação',required=False,choices=[('-date','Mais recentes'),('date','Mais antigas'),('invoice_number','NF')])
