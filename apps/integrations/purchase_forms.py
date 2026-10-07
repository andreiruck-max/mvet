from decimal import Decimal
from django import forms
from apps.inventory.models import StockLocation
from apps.products.models import Product
from apps.purchases.models import Supplier, Purchase
from apps.expenses.models import ChartOfAccount
from .forms import QueryForm, MoneyInput


class PurchaseQueryForm(QueryForm):
    source_status = forms.TypedChoiceField(label='Situação no Bling', coerce=int, choices=[(7, 'Registradas'), (5, 'Autorizadas'), (2, 'Canceladas — conferir divergências')])


class PurchaseReviewForm(forms.Form):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    supplier = forms.ModelChoiceField(label='Fornecedor', queryset=Supplier.objects.filter(active=True))
    location = forms.ModelChoiceField(label='Estoque de destino', queryset=StockLocation.objects.filter(active=True))
    discount = forms.DecimalField(label='Desconto (R$)', max_digits=18, decimal_places=2, min_value=0, initial=Decimal('0'), localize=True, widget=MoneyInput)
    freight = forms.DecimalField(label='Frete de aquisição (R$)', max_digits=18, decimal_places=2, min_value=0, initial=Decimal('0'), localize=True, widget=MoneyInput)
    other_costs = forms.DecimalField(label='Outros custos de aquisição (R$)', max_digits=18, decimal_places=2, min_value=0, initial=Decimal('0'), localize=True, widget=MoneyInput)
    acquisition_kind=forms.ChoiceField(label='Tipo de entrada',choices=Purchase._meta.get_field('acquisition_kind').choices,initial='NORMAL',required=False)
    reviewed = forms.BooleanField(label='Conferi o documento: a Mercadovet é a destinatária, a finalidade fiscal é normal (não devolução, ajuste ou complemento) e o tipo de entrada, produtos e quantidades estão corretos.')

    def clean_acquisition_kind(self):return self.cleaned_data['acquisition_kind'] or 'NORMAL'


class LocalProductChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.sku} · {obj.name} ({obj.unit})'


class PurchaseProductForm(forms.Form):
    mode=forms.ChoiceField(label='Destino do item',choices=[('STOCK','Movimentar estoque'),('NEW','Cadastrar produto e movimentar estoque'),('NONSTOCK','Somente financeiro — sem estoque')],initial='STOCK',required=False)
    product = LocalProductChoice(label='Produto MVet', required=False, queryset=Product.objects.filter(active=True, kind='SIMPLE').order_by('name'))
    category=forms.ModelChoiceField(label='Categoria sem estoque',required=False,queryset=ChartOfAccount.objects.filter(active=True,postable=True).exclude(nature='REVENUE'))
    new_sku=forms.CharField(label='SKU do novo produto',max_length=60,required=False)
    new_name=forms.CharField(label='Nome no MVet',max_length=240,required=False)
    new_unit=forms.CharField(label='Unidade no MVet',max_length=12,initial='UN',required=False)

    def clean(self):
        data=super().clean();mode=data.get('mode') or 'STOCK';data['mode']=mode
        if mode=='STOCK' and not data.get('product'):self.add_error('product','Selecione o produto ou escolha cadastrar um novo.')
        if mode=='NEW':
            for field in ('new_sku','new_name','new_unit'):
                if not data.get(field):self.add_error(field,'Preencha para cadastrar o produto.')
            data['product']=None
        if mode!='NONSTOCK':data['category']=None
        else:data['product']=None
        return data

PurchaseProducts = forms.formset_factory(PurchaseProductForm, extra=0, min_num=1, validate_min=True, max_num=100, validate_max=True)
