from uuid import uuid4
from decimal import Decimal
from django import forms
from django.utils import timezone
from apps.sales.models import Sale
from apps.crm.forms import DateInput
from .models import Payee

class ActionForm(forms.Form):
    key=forms.UUIDField(initial=uuid4,widget=forms.HiddenInput)
    reason=forms.CharField(label='Motivo / observação',max_length=500,widget=forms.Textarea(attrs={'rows':2}))

class PlanForm(ActionForm):
    sale=forms.ModelChoiceField(label='Venda confirmada',queryset=Sale.objects.none())
    payee=forms.ModelChoiceField(label='Comissionado',queryset=Payee.objects.filter(active=True))
    customer=forms.CharField(label='Cliente (somente identificação)',max_length=240,required=False)
    rate=forms.DecimalField(label='Percentual manual (%) — vazio usa o padrão',min_value=0,max_value=100,max_digits=7,decimal_places=4,required=False)
    count=forms.IntegerField(label='Quantidade de parcelas iguais',min_value=1,max_value=60,initial=1)
    first_date=forms.DateField(label='Primeiro vencimento',initial=timezone.localdate,widget=DateInput())
    days=forms.IntegerField(label='Intervalo entre parcelas (dias)',min_value=1,max_value=365,initial=30)
    schedule=forms.CharField(label='Parcelas com valores diferentes (opcional)',required=False,max_length=5000,
        help_text='Uma por linha: DD/MM/AAAA;valor. Ex.: 10/11/2026;475,00. Se preenchido, substitui as parcelas iguais.',widget=forms.Textarea(attrs={'rows':3}))
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['sale'].queryset=Sale.objects.filter(status='CONFIRMED',commission_plan__isnull=True).order_by('-date','-pk')
        self.fields['sale'].label_from_instance=lambda s:f'{s.reference} / {s.invoice_series or "—"} · {s.date:%d/%m/%Y} · R$ {s.products_amount-s.discount+s.shipping_received:.2f}'
    def clean(self):
        from datetime import datetime,timedelta
        from decimal import Decimal,InvalidOperation
        from .services import rounded
        d=super().clean();rows=[]
        if d.get('schedule'):
            try:
                for line in d['schedule'].splitlines():
                    if not line.strip():continue
                    date,amount=line.split(';')
                    value=amount.strip()
                    if ',' in value:value=value.replace('.','').replace(',','.')
                    rows.append((datetime.strptime(date.strip(),'%d/%m/%Y').date(),Decimal(value)))
            except (ValueError,InvalidOperation):raise forms.ValidationError('Parcelas: use uma linha por data e valor, como 10/11/2026;475,00.')
        elif all(d.get(x) is not None for x in ('sale','count','first_date','days')):
            sale=d['sale'];face=sale.products_amount-sale.discount+sale.shipping_received;allocated=Decimal(0)
            for n in range(d['count']):
                target=rounded(face*Decimal(n+1)/d['count'])
                rows.append((d['first_date']+timedelta(days=n*d['days']),target-allocated));allocated=target
        d['installments']=rows
        return d

class ReceiptForm(ActionForm):
    amount=forms.DecimalField(label='Valor recebido (R$)',min_value=Decimal('.01'),max_digits=18,decimal_places=2)
    date=forms.DateField(label='Data efetiva do recebimento',initial=timezone.localdate,widget=DateInput())

class ReverseForm(ActionForm):
    date=forms.DateField(label='Data efetiva do estorno',initial=timezone.localdate,widget=DateInput())

class ScheduleActionForm(ActionForm):
    revision=forms.IntegerField(widget=forms.HiddenInput)

class ScheduleRow(forms.Form):
    installment_id=forms.IntegerField(widget=forms.HiddenInput)
    due_date=forms.DateField(label='Vencimento',widget=DateInput())
    amount=forms.DecimalField(label='Valor da parcela (R$)',min_value=Decimal('.01'),max_digits=18,decimal_places=2)

ScheduleRows=forms.formset_factory(ScheduleRow,extra=0,max_num=60,validate_max=True,min_num=1,validate_min=True)

class AdjustForm(ActionForm):
    revision=forms.IntegerField(widget=forms.HiddenInput)
    rate=forms.DecimalField(label='Percentual (%)',min_value=0,max_value=100,max_digits=7,decimal_places=4)
    override_total=forms.DecimalField(label='Comissão total manual (R$) — opcional',min_value=0,max_digits=18,decimal_places=2,required=False,
        help_text='Vazio calcula pela base × percentual. Um valor preenchido substitui esse cálculo e fica identificado no histórico.')

class PaymentForm(ActionForm):
    payee=forms.ModelChoiceField(label='Comissionado',queryset=Payee.objects.all())
    amount=forms.DecimalField(label='Valor pago (R$)',min_value=Decimal('.01'),max_digits=18,decimal_places=2)
    date=forms.DateField(label='Data efetiva do pagamento',initial=timezone.localdate,widget=DateInput())
    period=forms.DateField(label='Mês de apuração (qualquer dia do mês)',initial=timezone.localdate,widget=DateInput())
    method=forms.CharField(label='Forma de pagamento',max_length=100,initial='PIX')

class PayeeForm(forms.ModelForm):
    class Meta:
        model=Payee
        fields=['name','kind','user','default_rate','active']
        labels={'default_rate':'Percentual padrão (%) — vazio usa o global'}

class DefaultForm(forms.Form):
    rate=forms.DecimalField(label='Percentual padrão global (%)',min_value=0,max_value=100,max_digits=7,decimal_places=4)
    reason=forms.CharField(label='Motivo',max_length=500)

class FilterForm(forms.Form):
    payee=forms.ModelChoiceField(label='Comissionado',queryset=Payee.objects.all(),required=False)
    q=forms.CharField(label='Cliente / NF / venda',required=False)
    start=forms.DateField(label='Venda de',widget=DateInput(),required=False)
    end=forms.DateField(label='Venda até',widget=DateInput(),required=False)
    received_start=forms.DateField(label='Recebimento de',widget=DateInput(),required=False)
    received_end=forms.DateField(label='Recebimento até',widget=DateInput(),required=False)
    state=forms.ChoiceField(label='Comissão',required=False,choices=[('','Todas'),('FORECAST','Prevista'),('PARTIAL','Parcialmente liberada'),('RELEASED','Totalmente liberada'),('PART_PAID','Parcialmente paga'),('PAID','Totalmente paga'),('CANCELLED','Cancelada'),('NEGATIVE','A compensar')])
    receipt=forms.ChoiceField(label='Recebimento da venda',required=False,choices=[('','Todos'),('OPEN','Não recebida'),('PARTIAL','Parcial'),('FULL','Integral')])
    payment=forms.ChoiceField(label='Pagamento',required=False,choices=[('','Todos'),('PENDING','Pendente'),('PAID','Pago'),('UNPAID','Sem pagamento')])
    def __init__(self,*args,actor,**kwargs):
        super().__init__(*args,**kwargs)
        if not actor.has_perm('core.manage_commissions'):self.fields.pop('payee')
    def clean(self):
        d=super().clean()
        for a,b in [('start','end'),('received_start','received_end')]:
            if d.get(a) and d.get(b) and d[a]>d[b]:raise forms.ValidationError('Intervalo de datas inválido.')
        return d

class MonthForm(forms.Form):
    month=forms.DateField(label='Mês de apuração',input_formats=['%Y-%m'],widget=forms.DateInput(format='%Y-%m',attrs={'type':'month'}))
    payee=forms.ModelChoiceField(label='Comissionado',queryset=Payee.objects.all(),required=False)
    def __init__(self,*args,actor,**kwargs):
        super().__init__(*args,**kwargs)
        if not actor.has_perm('core.manage_commissions'):self.fields.pop('payee')
