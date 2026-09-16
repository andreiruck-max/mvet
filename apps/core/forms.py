from django import forms
from .models import Company

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "minimum_margin"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["minimum_margin"].localize = True
        self.fields["minimum_margin"].widget = forms.TextInput(attrs={"inputmode": "decimal"})
