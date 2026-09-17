from uuid import uuid4
from decimal import Decimal
from datetime import timedelta
from django import forms
from django.utils import timezone
from .models import FinancialAccount as Account, FinancialTitle as Title


class DateInput(forms.DateInput):
    input_type='date'
    def __init__(self): super().__init__(format='%Y-%m-%d')


class AccountForm(forms.ModelForm):
    class Meta:
        model=Account
        fields=['name','institution','kind','opening_balance','opening_date','active']
        widgets={'opening_date':DateInput()}


class TitleForm(forms.ModelForm):
    key=forms.UUIDField(initial=uuid4,widget=forms.HiddenInput)
    class Meta:
        model=Title
        fields=['direction','description','counterparty','date','due_date','amount','account','category','opening','notes']
        widgets={'date':DateInput(),'due_date':DateInput()}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['account'].queryset=Account.objects.filter(active=True)
        self.fields['date'].initial=timezone.localdate
        self.fields['due_date'].initial=timezone.localdate


class ScheduleForm(forms.Form):
    due_date=forms.DateField(label='Novo vencimento',widget=DateInput())
    account=forms.ModelChoiceField(label='Conta prevista',queryset=Account.objects.filter(active=True),required=False)
    notes=forms.CharField(label='Observação',max_length=500,required=False)
    revision=forms.IntegerField(widget=forms.HiddenInput)


class SettlementForm(forms.Form):
    key=forms.UUIDField(initial=uuid4,widget=forms.HiddenInput)
    revision=forms.IntegerField(widget=forms.HiddenInput)
    account=forms.ModelChoiceField(label='Conta efetiva',queryset=Account.objects.filter(active=True))
    date=forms.DateField(label='Data efetiva',widget=DateInput(),initial=timezone.localdate)
    principal=forms.DecimalField(label='Principal a baixar (R$)',max_digits=18,decimal_places=2,min_value=Decimal('0.01'))
    interest=forms.DecimalField(label='Juros / acréscimos (R$)',initial=0,max_digits=18,decimal_places=2,min_value=0)
    discount=forms.DecimalField(label='Desconto / abatimento (R$)',initial=0,max_digits=18,decimal_places=2,min_value=0)
    actual=forms.DecimalField(label='Valor efetivamente pago / recebido (R$)',max_digits=18,decimal_places=2,min_value=0)
    notes=forms.CharField(label='Observação / motivo das diferenças',max_length=500,required=False)


class TransferForm(forms.Form):
    key=forms.UUIDField(initial=uuid4,widget=forms.HiddenInput)
    source=forms.ModelChoiceField(label='Conta de origem',queryset=Account.objects.filter(active=True))
    destination=forms.ModelChoiceField(label='Conta de destino',queryset=Account.objects.filter(active=True))
    date=forms.DateField(label='Data',widget=DateInput(),initial=timezone.localdate)
    amount=forms.DecimalField(label='Valor (R$)',max_digits=18,decimal_places=2,min_value=Decimal('0.01'))
    notes=forms.CharField(label='Descrição',max_length=500,required=False)
    planned=forms.BooleanField(label='Apenas prevista (ainda não movimentou dinheiro)',required=False)


class ReverseForm(forms.Form):
    date=forms.DateField(label='Data efetiva',widget=DateInput(),initial=timezone.localdate)
    reason=forms.CharField(label='Motivo',max_length=500)


class FilterForm(forms.Form):
    q=forms.CharField(label='Descrição / favorecido',required=False)
    direction=forms.ChoiceField(label='Tipo',choices=[('','Todos'),*Title.DIRECTIONS],required=False)
    status=forms.ChoiceField(label='Situação',choices=[('pending','Pendentes'),('overdue','Vencidos'),('paid','Liquidados'),('cancelled','Cancelados'),('all','Todos')],required=False)
    account=forms.ModelChoiceField(label='Conta',queryset=Account.objects.all(),required=False)
    category=forms.ChoiceField(label='Classificação',choices=[('','Todas'),*Title.CATEGORIES],required=False)
    start=forms.DateField(label='Vencimento de',widget=DateInput(),required=False)
    end=forms.DateField(label='Vencimento até',widget=DateInput(),required=False)
    sort=forms.ChoiceField(label='Ordenação',choices=[('due_date','Vencimento crescente'),('-due_date','Vencimento decrescente'),('-amount','Maior valor')],required=False)


class CashForm(forms.Form):
    start=forms.DateField(label='De',widget=DateInput(),initial=timezone.localdate)
    end=forms.DateField(label='Até',widget=DateInput(),initial=lambda:timezone.localdate()+timedelta(days=30))
    account=forms.ModelChoiceField(label='Conta',queryset=Account.objects.all(),required=False)
    def clean(self):
        data=super().clean()
        if data.get('start') and data.get('end') and not 0<=(data['end']-data['start']).days<=61:
            raise forms.ValidationError('Selecione até 62 dias, em ordem cronológica.')
        return data
