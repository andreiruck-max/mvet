"""Monthly seller statements using the same authorized historical projection as HTML."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from apps.core.models import Company
from apps.core.services import audit
from apps.reporting.datasets import Dataset
from apps.reporting.files import xlsx
from .models import Payment

NOTES = ('A comissão é liberada conforme o recebimento das parcelas. Base da venda = produtos menos descontos, sem frete. '
         'O total aplicado pode incluir ajuste manual; parcelas e recebimentos liberam valores proporcionais, com arredondamento. '
         'Ajustes e estornos entram na data efetiva. Pago no mês considera a data do pagamento; pago da apuração considera '
         'as alocações às liberações do mês até o corte. Pendente anterior é o saldo das liberações anteriores após essas alocações. '
         'Total a pagar/compensar = pendente anterior + pendente do mês. Saldo negativo é compensação. '
         'O relatório inclui os registros existentes até a emissão, com corte no encerramento do mês.')


def datasets(rows, events, payments, start, end):
    notes = f'Apuração: {start:%d/%m/%Y} a {end:%d/%m/%Y}. ' + NOTES
    summary = Dataset('Comissões - resumo',
        ['Comissionado', 'Liberada no mês', 'Pago no mês', 'Pago da apuração',
         'Pendente do mês', 'Pendente anterior', 'Total a pagar / compensar'],
        [[str(r['payee'])] + [r[k] for k in ('released','paid','month_allocated','pending','previous','total')] for r in rows], notes)
    detail = Dataset('Liberações e ajustes',
        ['Comissionado','Venda','Data da venda','Cliente','Parcela','Data da liberação','Base da venda aplicada',
         'Percentual aplicado (%)','Comissão total aplicada','Comissão prevista da parcela','Valor da parcela',
         'Recebimento / estorno','Liberada / ajuste','Paga até o corte','Pendente','Origem'],
        [[str(e.installment.plan.payee),e.installment.plan.sale.reference,e.installment.plan.sale.date,
          e.installment.plan.customer,e.installment.number,e.date,Decimal(e.terms['base']),
          Decimal(e.terms['rate']),Decimal(e.terms['total']),Decimal(e.terms['installment_forecast']),
          Decimal(e.terms['installment_amount']),e.received,e.released,e.paid,e.pending,e.command.reason] for e in events], notes)
    paid = Dataset('Pagamentos no mês',['Comissionado','Data','Mês de apuração','Valor','Forma','Tipo','Observação'],
        [[str(p.payee),p.date,p.period,p.amount,p.method,'Estorno' if p.reversal_of_id else 'Pagamento',p.command.reason] for p in payments], notes)
    summary.sections = [detail, paid]
    return summary


def render_pdf(rows, events, payments, start, end, company):
    from reportlab.platypus import PageBreak, Spacer
    from apps.reporting.pdf_layout import Report, p, fmt, table, HEADING, SECTION, SMALL, HEADER, NUMBER
    report = Report('Demonstrativo de comissões', company, wide=True)
    story = []
    for index, row in enumerate(rows):
        if index:
            story.append(PageBreak())
        person = row['payee']
        story += [p('Demonstrativo de comissões', HEADING), p(str(person), SECTION),
                  p(f'Apuração: {start:%d/%m/%Y} a {end:%d/%m/%Y}', SMALL), p(NOTES, SMALL), Spacer(1, 10)]
        summary = datasets([row], [], [], start, end)
        data = [[p(h, HEADER) for h in summary.headers[1:]],
                [p(v, NUMBER) for v in summary.rows[0][1:]]]
        story += [table(data, [report.width/6]*6), p('Liberações, ajustes e pendências anteriores', SECTION)]
        detail = [[p(h, HEADER) for h in ['Venda / cliente','Parcela / liberação','Base / termos aplicados','Recebido / estorno','Liberada / ajuste','Paga até o corte','Pendente']]]
        for e in events:
            if e.installment.plan.payee_id != person.pk:
                continue
            plan = e.installment.plan
            terms = (f"Base: {fmt(Decimal(e.terms['base']))}\n"
                     'Percentual: ' + format(Decimal(e.terms['rate']), '.4f').replace('.', ',') + '%\n'
                     f"Total aplicado: {fmt(Decimal(e.terms['total']))}\n"
                     f"Previsto da parcela: {fmt(Decimal(e.terms['installment_forecast']))}")
            detail.append([p(f'{plan.sale.reference}\n{plan.sale.date:%d/%m/%Y} · {plan.customer}\n{e.command.reason}'),
                           p(f'{e.installment.number}\n{e.date:%d/%m/%Y}'),p(terms),
                           p(e.received, NUMBER),p(e.released, NUMBER),p(e.paid, NUMBER),p(e.pending, NUMBER)])
        if len(detail) == 1:
            detail.append([p('Sem liberações ou pendências.')]+[p('') for _ in range(6)])
        story.append(table(detail, [report.width*w for w in (.25,.10,.23,.105,.105,.105,.105)]))
        story.append(p('Pagamentos e estornos realizados no mês', SECTION))
        data = [[p(h,HEADER) for h in ['Data','Forma','Tipo','Valor','Observação']]]
        for payment in payments:
            if payment.payee_id == person.pk:
                data.append([p(payment.date),p(payment.method),p('Estorno' if payment.reversal_of_id else 'Pagamento'),
                             p(payment.amount,NUMBER),p(payment.command.reason)])
        if len(data) == 1:
            data.append([p('Sem pagamentos no mês.')]+[p('') for _ in range(4)])
        story.append(table(data,[report.width*w for w in (.12,.14,.12,.14,.48)]))
    if not story:
        story = [p('Demonstrativo de comissões', HEADING),p('Nenhum comissionado encontrado.')]
    return report.build(story)


def export_monthly(request, month, payee=None):
    file_format = request.GET.get('export')
    if file_format not in ('pdf', 'xlsx'):
        raise ValidationError('Formato de exportação inválido.')
    from django.db import transaction
    from apps.inventory.services import domain_lock
    from .selectors import monthly
    with transaction.atomic():
        domain_lock()
        rows, events, start, end = monthly(request.user, month, payee)
        payments = list(Payment.objects.filter(payee_id__in=[r['payee'].pk for r in rows],date__range=(start,end))
                    .select_related('payee','command').order_by('payee__name','date','pk'))
    limit = 2000 if file_format == 'pdf' else 10000
    if len(events)+len(payments)+len(rows) > limit:
        raise ValidationError(f'Limite de {limit} registros. Filtre um comissionado; nenhum registro foi omitido.')
    company = Company.objects.get(pk=1)
    content = (xlsx(datasets(rows, events, payments, start, end), company.name) if file_format == 'xlsx'
               else render_pdf(rows, events, payments, start, end, company.name))
    audit(request.user, company, 'export_report', after={'report':'commissions_monthly','format':file_format,
        'month':start.isoformat(),'payees':[r['payee'].pk for r in rows],'events':len(events)})
    response = HttpResponse(content,content_type='application/pdf' if file_format == 'pdf' else
                            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="mvet-comissoes-{start:%Y-%m}.{file_format}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
