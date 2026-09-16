from django import forms
from .models import Company

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "minimum_margin", "default_stock_location"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.inventory.models import StockLocation
        self.fields["default_stock_location"].queryset=StockLocation.objects.filter(active=True)
        self.fields["default_stock_location"].help_text="Será sugerido em novas vendas; pode ser alterado no lançamento."
        self.fields["minimum_margin"].localize = True
        self.fields["minimum_margin"].widget = forms.TextInput(attrs={"inputmode": "decimal"})
