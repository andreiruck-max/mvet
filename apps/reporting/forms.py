import calendar
from datetime import timedelta
from django import forms
from django.utils import timezone
from apps.finance.forms import DateInput
from apps.sales.models import SalesChannel
from apps.purchases.models import Supplier

class PeriodForm(forms.Form):
    period=forms.ChoiceField(label='Período',required=False,choices=[('','Personalizado'),('today','Hoje'),('yesterday','Ontem'),('last7','Últimos 7 dias'),('week','Semana'),('month','Mês'),('previous_month','Mês anterior'),('year','Ano')])
    start=forms.DateField(label='De',widget=DateInput(),required=False)
    end=forms.DateField(label='Até',widget=DateInput(),required=False)
    channel=forms.ModelChoiceField(label='Canal das vendas',queryset=SalesChannel.objects.all(),required=False)
    def clean(self):
        d=super().clean();today=timezone.localdate();p=d.get('period');a,b=d.get('start'),d.get('end')
        if p=='today':a=b=today
        elif p=='yesterday':a=b=today-timedelta(days=1)
        elif p=='last7':a=today-timedelta(days=6);b=today
        elif p=='week':a=today-timedelta(days=today.weekday());b=a+timedelta(days=6)
        elif p=='month':a=today.replace(day=1);b=today.replace(day=calendar.monthrange(today.year,today.month)[1])
        elif p=='previous_month':b=today.replace(day=1)-timedelta(days=1);a=b.replace(day=1)
        elif p=='year':a=today.replace(month=1,day=1);b=today.replace(month=12,day=31)
        if not a or not b:raise forms.ValidationError('Selecione um período ou informe as duas datas.')
        if not 0<=(b-a).days<=365:raise forms.ValidationError('Selecione até 366 dias, em ordem cronológica.')
        d.update(start=a,end=b);return d

class SalesForm(PeriodForm):
    q=forms.CharField(label='NF',required=False)
    status=forms.ChoiceField(label='Situação',required=False,choices=[('CONFIRMED','Confirmadas'),('DRAFT','Rascunhos'),('CANCELLED','Canceladas'),('all','Todas')])
    sort=forms.ChoiceField(label='Ordenar',required=False,choices=[('date','Data e NF crescentes'),('-date','Mais recentes'),('-products_amount','Maior valor')],initial='date')

class PayablesForm(PeriodForm):
    channel=None
    period=forms.ChoiceField(label='Vencimentos', required=False, choices=[('future','Hoje em diante'),('all','Todas as datas'),('', 'Personalizado'),('month','Este mês'),('previous_month','Mês anterior'),('year','Este ano')])
    supplier=forms.ModelChoiceField(label='Fornecedor',queryset=Supplier.objects.all(),required=False)
    purchase_start=forms.DateField(label='Compra de',widget=DateInput(),required=False)
    purchase_end=forms.DateField(label='Compra até',widget=DateInput(),required=False)
    status=forms.ChoiceField(label='Situação',required=False,choices=[('pending','Pendentes'),('paid','Pagas'),('all','Todas não canceladas')])
    def clean(self):
        raw=forms.Form.clean(self)
        period=raw.get('period')
        if period in ('future','all') or (not period and not raw.get('start') and not raw.get('end') and not self.errors):
            d=raw
            d.update(start=timezone.localdate() if period != 'all' else None, end=None)
        else:
            d=super().clean()
        if d.get('purchase_start') and d.get('purchase_end') and d['purchase_start']>d['purchase_end']:raise forms.ValidationError('Intervalo da compra inválido.')
        return d
