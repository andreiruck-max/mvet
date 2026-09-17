from uuid import uuid4
from django import forms
from django.utils import timezone
from apps.finance.forms import DateInput
from apps.finance.models import FinancialAccount
from apps.purchases.models import Supplier
from .models import ChartOfAccount, ClassificationRule, Expense


class CategoryForm(forms.ModelForm):
    class Meta:
        model=ChartOfAccount
        fields=['code','name','parent','nature','postable','active']
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['parent'].queryset=ChartOfAccount.objects.filter(postable=False,active=True).exclude(pk=self.instance.pk)


class RuleForm(forms.ModelForm):
    class Meta:
        model=ClassificationRule
        fields=['name','priority','field','operator','value','category','active']


class ExpenseForm(forms.ModelForm):
    key=forms.UUIDField(initial=uuid4,widget=forms.HiddenInput)
    due_date=forms.DateField(label='Vencimento',initial=timezone.localdate,widget=DateInput())
    account=forms.ModelChoiceField(label='Conta prevista',queryset=FinancialAccount.objects.filter(active=True),required=False)
    class Meta:
        model=Expense
        fields=['description','amount','competence','document_date','supplier','counterparty','category','cost_center','notes','recurrence_enabled']
        widgets={'competence':DateInput(),'document_date':DateInput()}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['competence'].initial=timezone.localdate
        self.fields['document_date'].initial=timezone.localdate
        self.fields['category'].queryset=ChartOfAccount.objects.filter(active=True,postable=True,nature__in=['OPERATING','FINANCIAL'])
        self.fields['category'].empty_label='Aplicar regras / deixar a classificar'
        self.fields['supplier'].queryset=Supplier.objects.filter(active=True)


class ReclassifyForm(forms.Form):
    category=forms.ModelChoiceField(label='Nova categoria',queryset=ChartOfAccount.objects.filter(active=True,postable=True,nature__in=['OPERATING','FINANCIAL']),required=False)
    automatic=forms.BooleanField(label='Aplicar regras atuais',required=False)
    cost_center=forms.CharField(label='Centro de custo',max_length=120,required=False)
    reason=forms.CharField(label='Motivo da correção',max_length=500)
    revision=forms.IntegerField(widget=forms.HiddenInput)


class CancelForm(forms.Form):
    reason=forms.CharField(label='Motivo do cancelamento',max_length=500)


class RecurrenceForm(forms.Form):
    months=forms.IntegerField(label='Próximos meses (1 a 24)',min_value=1,max_value=24,initial=3)
    preview_hash=forms.CharField(required=False,widget=forms.HiddenInput)


class FilterForm(forms.Form):
    q=forms.CharField(label='Descrição / favorecido',required=False)
    period=forms.ChoiceField(label='Período de competência',required=False,choices=[('','Personalizado'),('today','Hoje'),('yesterday','Ontem'),('week','Semana'),('month','Mês'),('previous_month','Mês anterior'),('year','Ano')])
    start=forms.DateField(label='Competência de',widget=DateInput(),required=False)
    end=forms.DateField(label='Competência até',widget=DateInput(),required=False)
    category=forms.ModelChoiceField(label='Categoria e subcategorias',queryset=ChartOfAccount.objects.all(),required=False)
    supplier=forms.ModelChoiceField(label='Fornecedor',queryset=Supplier.objects.all(),required=False)
    cost_center=forms.CharField(label='Centro de custo',required=False)
    status=forms.ChoiceField(label='Situação',required=False,choices=[('active','Registradas'),('pending','Pendentes'),('paid','Pagas'),('overdue','Vencidas'),('future','Competência futura'),('unclassified','A classificar'),('cancelled','Canceladas'),('all','Todas')])
    def clean(self):
        data=super().clean()
        if data.get('start') and data.get('end') and data['start']>data['end']:raise forms.ValidationError('Período inválido.')
        return data
