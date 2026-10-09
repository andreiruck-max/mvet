from decimal import Decimal, ROUND_HALF_UP
from django import forms
from django.utils import timezone
from apps.sales.forms import SaleForm
from apps.products.models import Product


class QueryForm(forms.Form):
    number=forms.IntegerField(label='Buscar NF específica (opcional)',required=False,min_value=1,max_value=999999999,help_text='Com número informado, consulta diretamente no Bling sem limitar data ou situação.')
    series=forms.IntegerField(label='Série da NF (opcional)',required=False,min_value=0,max_value=999)
    start = forms.DateField(label='Emissão de', initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    end = forms.DateField(label='Até', initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    page = forms.IntegerField(label='Página do Bling', min_value=1, max_value=10000, initial=1, widget=forms.HiddenInput)
    source_status = forms.TypedChoiceField(label='Situação no Bling', coerce=int, choices=[(56, 'Autorizadas + Emitida DANFE'), (5, 'Autorizadas'), (6, 'Emitida DANFE'), (2, 'Canceladas — conferir divergências')], initial=56)


class ReviewForm(SaleForm):
    def __init__(self, *args, invoice, **kwargs):
        super().__init__(*args, **kwargs)
        for field, value in [('date', invoice.issued_on), ('invoice_number', invoice.number), ('invoice_series', invoice.series)]:
            self.fields[field].disabled = True
            self.initial[field] = value
        self.initial['revision'] = invoice.revision
        from apps.sales.taxes import suggested_rule
        self.initial['tax_rule'] = suggested_rule(invoice.issued_on or timezone.localdate())
        # Submission of the confirmation button is the review action.
        for name in ['channel', 'location', 'tax_rule']:
            self.fields[name].required = True
        for name in ['tax_override', 'tax_reason']:
            self.fields[name].disabled = True
            self.fields[name].widget = forms.HiddenInput()
        self.initial.update(tax_override=None, tax_reason='')
        self.optional_fields = [f for f in self.optional_fields if f.name not in ('tax_override', 'tax_reason')]
        from apps.sales.services import FINANCIAL_FIELDS
        for name in FINANCIAL_FIELDS:
            self.initial[name] = Decimal('0.00')
            self.fields[name].localize = True
            self.fields[name].widget = MoneyInput(attrs={'inputmode': 'decimal'})
        if 'revenue_target' in self.fields:
            # Optional target is not a deduction: zero would reset the revenue.
            self.fields['revenue_target'].localize = True
            self.fields['revenue_target'].widget = MoneyInput(attrs={'inputmode': 'decimal', 'placeholder': '0,00'})
        if invoice.source:
            amount = sum((Decimal(i['quantity']) * Decimal(i['price']) for i in invoice.source['items']), Decimal(0))
            self.initial['products_amount'] = amount.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
            self.initial['shipping_received'] = Decimal(invoice.source.get('freight', '0'))
            self.initial['shipping_paid'] = self.initial['shipping_received']
        from .models import ReviewDefaults
        defaults = ReviewDefaults.objects.select_related('full_channel', 'full_location', 'default_channel', 'default_location').filter(pk=1).first()
        self.routing_missing = defaults is None
        if defaults:
            prefix = 'full' if invoice.source.get('store') == defaults.full_store else 'default'
            for field in ('channel', 'location'):
                obj = getattr(defaults, prefix + '_' + field)
                self.initial[field] = obj.pk if obj.active else None
        self.initial.update(invoice.review_overrides)
        self.fields['shipping_received'].help_text = 'Frete da nota no Bling; confira e altere se necessário.'
        self.fields['shipping_paid'].help_text = 'Sugerido igual ao frete da nota. Ajuste para o custo efetivamente pago.'
        self.fields['discount'].help_text = 'Não fornecido nesta consulta do Bling. Confira e informe se houver.'

    def clean(self):
        data = super().clean()
        data['tax_override'] = None
        data['tax_reason'] = ''
        return data


class MoneyInput(forms.TextInput):
    def format_value(self, value):
        if isinstance(value, Decimal):
            return format(value, '.2f').replace('.', ',')
        return super().format_value(value)


from .models import ReviewDefaults


class ReviewDefaultsForm(forms.ModelForm):
    class Meta:
        model = ReviewDefaults
        fields = ['full_store', 'full_channel', 'full_location', 'default_channel', 'default_location']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.Meta.fields[1:]:
            self.fields[name].queryset = self.fields[name].queryset.filter(active=True)

    def clean_full_store(self):
        value = self.cleaned_data['full_store'].strip()
        if not value.isascii() or not value.isdecimal():
            raise forms.ValidationError('Informe o identificador numérico da loja Full.')
        return value


class AliasForm(forms.Form):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    code = forms.CharField(label='Código externo', max_length=120)
    product = forms.ModelChoiceField(label='Produto MVet', queryset=Product.objects.filter(active=True), widget=forms.HiddenInput(attrs={'data-product-lookup': 'true'}))

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        if invoice is not None:
            choices = dict((row['code'], f"{row['code']} · {row['name']}") for row in invoice.source.get('items', []) if row['code'])
            self.fields['code'] = forms.ChoiceField(label='Item da nota', choices=list(choices.items()))


class DecisionForm(forms.Form):
    revision = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(label='Motivo', max_length=500)


from apps.sales.forms import ExtraCostForm, MasterExtraCostForm


class ReviewExtraCostForm(ExtraCostForm):
    amount = forms.DecimalField(label='Valor (R$)', max_digits=18, decimal_places=2,
                                min_value=0, initial=Decimal('0.00'), localize=True,
                                widget=MoneyInput(attrs={'inputmode': 'decimal'}))


class ReviewMasterExtraCostForm(MasterExtraCostForm):
    amount = forms.DecimalField(label='Valor (R$)', max_digits=18, decimal_places=2,
                                min_value=0, initial=Decimal('0.00'), localize=True,
                                widget=MoneyInput(attrs={'inputmode': 'decimal'}))


ReviewExtraCosts = forms.formset_factory(ReviewExtraCostForm, extra=0, can_delete=True, max_num=100, validate_max=True)
ReviewMasterExtraCosts = forms.formset_factory(ReviewMasterExtraCostForm, extra=0, can_delete=True, max_num=100, validate_max=True)
