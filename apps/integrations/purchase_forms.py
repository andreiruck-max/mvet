from decimal import Decimal
from django import forms
from apps.inventory.models import StockLocation
from apps.products.models import Product
from apps.purchases.models import Supplier
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
    reviewed = forms.BooleanField(label='Conferi o documento: a Mercadovet é a destinatária, trata-se de compra normal de mercadorias, e os produtos e quantidades estão corretos.')


class LocalProductChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.sku} · {obj.name} ({obj.unit})'


class PurchaseProductForm(forms.Form):
    product = LocalProductChoice(label='Produto MVet', queryset=Product.objects.filter(active=True, kind='SIMPLE').order_by('name'))

PurchaseProducts = forms.formset_factory(PurchaseProductForm, extra=0, min_num=1, validate_min=True, max_num=100, validate_max=True)
