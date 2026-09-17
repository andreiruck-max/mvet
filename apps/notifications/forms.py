from django import forms
from .models import AlertConfiguration, KINDS
from .selectors import allowed_kinds


class PreferencesForm(forms.Form):
    enabled = forms.MultipleChoiceField(label='Alertas que desejo receber', choices=KINDS, widget=forms.CheckboxSelectMultiple, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['enabled'].choices = [(k, label) for k, label in KINDS if k in allowed_kinds(user)]


class ConfigurationForm(forms.ModelForm):
    class Meta:
        model = AlertConfiguration
        fields = ['stock', 'margin', 'due', 'due_days', 'backup', 'backup_hours']


class ReadForm(forms.Form):
    revision = forms.IntegerField(min_value=1)
