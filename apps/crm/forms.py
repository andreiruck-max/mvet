from uuid import uuid4
from django import forms
from django.utils import timezone
from .models import Contact, Interaction, RecurrenceRule
from . import choices as c
from .services import owners, phone_number

class DateInput(forms.DateInput):
    input_type='date'
    def __init__(self,*args,**kwargs):super().__init__(*args,format='%Y-%m-%d',**kwargs)

class ContactForm(forms.ModelForm):
    revision=forms.IntegerField(widget=forms.HiddenInput,initial=0)
    first_date=forms.DateField(label='Primeiro contato',initial=timezone.localdate,widget=DateInput(),required=False)
    class Meta:
        model=Contact
        fields=['name','phone','email','city','uf','company','segment','origin','kind','owner','commercial_info','notes']
        widgets={'commercial_info':forms.Textarea(attrs={'rows':3}),'notes':forms.Textarea(attrs={'rows':2})}
    def __init__(self,*args,actor,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['owner'].queryset=owners()
        self.fields['owner'].required=False
        if not actor.is_superuser: self.fields.pop('owner')
        if self.instance.pk:self.fields.pop('first_date')
    def clean_phone(self):return phone_number(self.cleaned_data['phone'])
    def clean_email(self):return self.cleaned_data['email'].strip().casefold()
    def clean(self):
        d=super().clean()
        if not d.get('phone') and not d.get('email'):raise forms.ValidationError('Informe telefone/WhatsApp ou e-mail.')
        return d

class InteractionForm(forms.ModelForm):
    sent=forms.CharField(label='Mensagem enviada',required=False,strip=False,max_length=20000,widget=forms.Textarea(attrs={'rows':3}))
    received=forms.CharField(label='Mensagem recebida',required=False,strip=False,max_length=20000,widget=forms.Textarea(attrs={'rows':3}))
    key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid4)
    revision=forms.IntegerField(widget=forms.HiddenInput)
    next_date=forms.DateField(label='Próximo contato (deixe vazio para usar a regra)',required=False,widget=DateInput())
    next_reason=forms.CharField(label='Motivo da próxima ação',max_length=300,required=False)
    class Meta:
        model=Interaction
        fields=['occurred_at','channel','kind','sent','received','read_state','result','internal_note']
        widgets={'occurred_at':forms.DateTimeInput(format='%Y-%m-%dT%H:%M',attrs={'type':'datetime-local'}),**{x:forms.Textarea(attrs={'rows':3}) for x in ('sent','received','internal_note')}}

class StateForm(forms.Form):
    revision=forms.IntegerField(widget=forms.HiddenInput)
    date=forms.DateField(label='Data de retorno',required=False,widget=DateInput())
    reason=forms.ChoiceField(label='Motivo',choices=c.REASONS,required=False)
    justification=forms.CharField(label='Justificativa / contexto',max_length=5000,widget=forms.Textarea(attrs={'rows':3}))
    owner=forms.ModelChoiceField(label='Responsável',queryset=Contact.objects.none(),required=False)
    def __init__(self,*args,action,**kwargs):
        super().__init__(*args,**kwargs);self.fields['owner'].queryset=owners()
        if action!='reactivate':self.fields.pop('owner')
        if action!='request':self.fields.pop('reason')
        if action in ('request','dnc'):self.fields.pop('date')

class DecisionForm(forms.Form):
    decision=forms.ChoiceField(label='Decisão',choices=[('approve','Aprovar inativação'),('reject','Recusar e definir retorno')])
    date=forms.DateField(label='Nova data (obrigatória ao recusar)',required=False,widget=DateInput())
    note=forms.CharField(label='Orientação do Master',max_length=5000,required=False,widget=forms.Textarea(attrs={'rows':3}))

class FilterForm(forms.Form):
    q=forms.CharField(label='Nome, telefone, e-mail, empresa ou cidade',required=False)
    owner=forms.ModelChoiceField(label='Responsável',queryset=Contact.objects.none(),required=False)
    city=forms.CharField(label='Cidade',required=False)
    segment=forms.ChoiceField(label='Segmento',choices=[('','Todos')]+c.SEGMENTS,required=False)
    origin=forms.ChoiceField(label='Origem',choices=[('','Todas')]+c.ORIGINS,required=False)
    state=forms.ChoiceField(label='Status',choices=[('','Todos')]+c.STATES,required=False)
    result=forms.ChoiceField(label='Último resultado',choices=[('','Todos')]+c.RESULTS,required=False)
    start=forms.DateField(label='Próxima ação de',required=False,widget=DateInput())
    end=forms.DateField(label='Próxima ação até',required=False,widget=DateInput())
    overdue=forms.BooleanField(label='Somente atrasados',required=False)
    def __init__(self,*args,actor,**kwargs):
        super().__init__(*args,**kwargs)
        from django.contrib.auth import get_user_model
        self.fields['owner'].queryset=get_user_model().objects.order_by('username')
        if not actor.is_superuser:self.fields.pop('owner')
    def clean(self):
        d=super().clean()
        if d.get('start') and d.get('end') and d['start']>d['end']:raise forms.ValidationError('Datas em ordem inválida.')
        return d

class RuleForm(forms.ModelForm):
    class Meta:
        model=RecurrenceRule
        fields=['days','allow_manual']
Rules=forms.modelformset_factory(RecurrenceRule,form=RuleForm,extra=0)

class ImportForm(forms.Form):
    file=forms.FileField(label='Lista CSV ou XLSX')
    owner=forms.ModelChoiceField(label='Responsável padrão',queryset=Contact.objects.none())
    first_date=forms.DateField(label='Primeira pendência',initial=timezone.localdate,widget=DateInput())
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.fields['owner'].queryset=owners()
