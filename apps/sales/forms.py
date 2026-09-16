import uuid
from decimal import Decimal
from django import forms
from django.utils import timezone
from apps.products.models import Product
from apps.inventory.models import StockLocation
from .models import Sale, SalesChannel, TaxRule
from .services import EDIT_FIELDS, FINANCIAL_FIELDS

class SaleForm(forms.ModelForm):
    key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    revision=forms.IntegerField(widget=forms.HiddenInput,initial=0)
    class Meta:
        model=Sale
        fields=EDIT_FIELDS
        widgets={'date':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'),'notes':forms.Textarea(attrs={'rows':2})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['date'].initial=timezone.localdate
        self.fields['channel'].queryset=SalesChannel.objects.filter(active=True)
        self.fields['location'].queryset=StockLocation.objects.filter(active=True)
        self.fields['tax_rule'].queryset=TaxRule.objects.filter(active=True)
        for name in ['channel','location','tax_rule']:
            if self.fields[name].queryset.count()==1:self.fields[name].initial=self.fields[name].queryset.first()
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
        return data

class ItemForm(forms.Form):
    product=forms.ModelChoiceField(label='Produto',queryset=Product.objects.filter(active=True),widget=forms.HiddenInput(attrs={'data-product-lookup':'true'}))
    quantity=forms.DecimalField(label='Quantidade',max_digits=18,decimal_places=4,min_value=Decimal('0.0001'),initial=1)

Items=forms.formset_factory(ItemForm,extra=1,can_delete=True,max_num=100,validate_max=True)

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

class FilterForm(forms.Form):
    q=forms.CharField(label='NF ou produto',required=False)
    start=forms.DateField(label='De',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    end=forms.DateField(label='Até',required=False,widget=forms.DateInput(attrs={'type':'date'}))
    channel=forms.ModelChoiceField(label='Canal',queryset=SalesChannel.objects.all(),required=False)
    status=forms.ChoiceField(label='Status',choices=[('','Todos'),*Sale._meta.get_field('status').choices],required=False)
    period=forms.ChoiceField(label='Período',required=False,choices=[('','Personalizado'),('today','Hoje'),('yesterday','Ontem'),('week','Semana'),('month','Mês'),('previous_month','Mês anterior'),('year','Ano')])
    sort=forms.ChoiceField(label='Ordenação',required=False,choices=[('-date','Mais recentes'),('date','Mais antigas'),('invoice_number','NF')])
