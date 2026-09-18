from decimal import Decimal
from django import forms
from django.utils import timezone
from apps.sales.forms import SaleForm
from apps.products.models import Product


class QueryForm(forms.Form):
    start = forms.DateField(label='Emissão de', initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    end = forms.DateField(label='Até', initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    page = forms.IntegerField(label='Página do Bling', min_value=1, max_value=10000, initial=1)
    source_status = forms.TypedChoiceField(label='Situação no Bling', coerce=int, choices=[(5, 'Autorizadas'), (2, 'Canceladas — conferir divergências')])


class ReviewForm(SaleForm):
    reviewed = forms.BooleanField(label='Conferi que esta nota é uma venda, os produtos, valores, deduções (inclusive zeros), canal e estoque.')
    def __init__(self, *args, invoice, **kwargs):
        super().__init__(*args, **kwargs)
        for field, value in [('date', invoice.issued_on), ('invoice_number', invoice.number), ('invoice_series', invoice.series)]:
            self.fields[field].disabled = True
            self.initial[field] = value
        self.initial['revision'] = invoice.revision
        # Unlike a manual draft, unknown deductions require an explicit value.
        for field in ['discount', 'shipping_paid', 'fees', 'difal', 'commission', 'other_costs']:
            self.fields[field].required = not bool(self.actor and self.actor.is_superuser)
            self.fields[field].initial = None
        self.fields['shipping_received'].required = not bool(self.actor and self.actor.is_superuser)
        if self.actor and self.actor.is_superuser: self.fields['reviewed'].required = False
        if invoice.source:
            amount = sum((Decimal(i['quantity']) * Decimal(i['price']) for i in invoice.source['items']), Decimal(0))
            self.initial['products_amount'] = amount.quantize(Decimal('.01'))
            self.initial['shipping_received'] = invoice.source['freight']

    def clean(self):
        data = super().clean()
        if self.actor and self.actor.is_superuser: data['reviewed'] = True
        return data


class AliasForm(forms.Form):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    code = forms.CharField(label='Código externo', max_length=120)
    unit = forms.CharField(label='Unidade externa', max_length=12)
    product = forms.ModelChoiceField(label='Produto MVet', queryset=Product.objects.filter(active=True), widget=forms.HiddenInput(attrs={'data-product-lookup': 'true'}))


class DecisionForm(forms.Form):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(label='Motivo', max_length=500)
