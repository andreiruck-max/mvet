"""Calendar comparisons and explicit scenarios over the official reporting sources."""
import calendar
from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.services import require
from apps.core.models import Company
from . import selectors
from .datasets import metrics_for

ZERO = Decimal('0')


def month_start(day, offset=0):
    value = day.year * 12 + day.month - 1 + offset
    year, month = divmod(value, 12)
    return date(year, month + 1, 1)


def month_end(day):
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def variation(current, previous):
    # Zero/negative bases do not support a meaningful growth percentage.
    return (current - previous) / previous * 100 if previous > 0 else None


def ranges(as_of, cutover, grouping):
    periods = []
    for offset in reversed(range(12 if grouping == 'month' else 5)):
        if grouping == 'month':
            start = month_start(as_of, -offset)
            end = month_end(start)
            comparable = start.replace(day=min(as_of.day, end.day))
        else:
            start = date(as_of.year-offset, 1, 1)
            end = date(start.year, 12, 31)
            comparable = date(start.year, as_of.month, min(as_of.day, calendar.monthrange(start.year,as_of.month)[1]))
        end = min(end, as_of)
        if end < cutover:
            continue
        actual_start = max(start, cutover)
        periods.append(dict(start=actual_start, end=end, comparable_end=min(comparable,end),
                            period=start, complete_start=start >= cutover,
                            comparable_available=comparable >= actual_start,
                            current=start.year == as_of.year and (grouping == 'year' or start.month == as_of.month)))
    return periods


def sales(start, end, channel):
    return selectors.sales_summary(selectors.sale_rows(dict(start=start,end=end,channel=channel)))


def estimate(current, previous, previous_to_date, *, as_of, cutover):
    """Return a scenario, never a confidence interval or a booking."""
    start = month_start(as_of)
    days = month_end(as_of).day
    if start < cutover:
        return dict(available=False, reason='O mês começa antes do início do histórico do MVet.')
    if not current['count'] or current['revenue'] <= 0:
        return dict(available=False, reason='Sem receita positiva de vendas confirmadas para estimar o ritmo do mês.')
    linear = current['revenue'] * Decimal(days) / Decimal(as_of.day)
    if as_of.day == days:
        revenue = current['revenue']
        method = 'Mês completo na data de corte'
        formula = 'O corte coincide com o último dia do mês: o cenário corresponde ao valor registrado.'
    elif month_start(as_of,-1) >= cutover and previous['revenue'] > 0 and previous_to_date['revenue'] > 0:
        revenue = previous['revenue'] * current['revenue'] / previous_to_date['revenue']
        method = 'Ritmo relativo ao mês anterior'
        formula = 'Receita do mês anterior inteiro × (receita atual até o corte ÷ receita anterior até o mesmo dia).'
    else:
        revenue = linear
        method = 'Ritmo diário (sem base anterior suficiente)'
        formula = 'Receita atual até o corte ÷ dias corridos observados × dias do mês.'
    factor = revenue / current['revenue']
    projected = selectors.metrics({**{key:current[key]*factor for key in selectors.FIELDS}, 'count':Decimal(current['count'])*factor})
    return dict(available=True, method=method, formula=formula, values=projected,
                linear_revenue=linear, days=as_of.day, month_days=days,
                previous_full=previous['revenue'], previous_to_date=previous_to_date['revenue'])


def report(actor, as_of, grouping='month', channel=None):
    require(actor, 'core.view_dashboard')
    cutover = Company.objects.get(pk=1).cutover_date
    if grouping not in ('month','year') or not cutover <= as_of <= timezone.localdate():
        raise ValidationError('Informe uma data entre o início do histórico do MVet e hoje.')
    can_result = actor.has_perm('core.view_dre') and not channel
    rows = []
    previous = None
    for period in ranges(as_of,cutover,grouping):
        full = sales(period['start'],period['end'],channel)
        comparable = (full if period['end'] == period['comparable_end'] else
                      sales(period['start'],period['comparable_end'],channel)) if period['comparable_available'] else None
        row = {**period, 'full':full, 'comparable':comparable}
        row['change'] = (variation(comparable['revenue'],previous['comparable']['revenue'])
                         if previous and previous['complete_start'] and period['complete_start'] and comparable and previous['comparable'] else None)
        # Whole-period growth is not claimed for an unfinished current period.
        row['full_change'] = (variation(full['revenue'],previous['full']['revenue'])
                              if previous and previous['complete_start'] and period['complete_start'] and
                              period['end'] == (month_end(period['period']) if grouping == 'month' else date(period['period'].year,12,31)) else None)
        row['daily_average'] = full['revenue'] / Decimal((period['end']-period['start']).days+1)
        if can_result:
            dre = selectors.dre(dict(start=period['start'],end=period['end']))
            row.update(result=dre['result'], provisional=dre['provisional'])
        rows.append(row)
        previous = row
    first = rows[0]['start']
    total = selectors.metrics({**{key:sum((r['full'][key] for r in rows),ZERO) for key in selectors.FIELDS},
                               'count':sum(r['full']['count'] for r in rows)})
    months = (as_of.year-first.year)*12+as_of.month-first.month+1
    days = (as_of-first).days+1
    average = selectors.metrics({**{key:total[key]/len(rows) for key in selectors.FIELDS}, 'count':Decimal(total['count'])/len(rows)})
    summary = dict(values=metrics_for(actor,total), average=metrics_for(actor,average), periods=len(rows), months=months, days=days,
                   monthly_revenue=total['revenue']/months, daily_revenue=total['revenue']/days,
                   average_sales=Decimal(total['count'])/months,
                   partial=first.day != 1 or as_of != month_end(as_of))
    if actor.has_perm('core.view_costs'):summary['monthly_cmv']=total['cmv']/months
    if actor.has_perm('core.view_margins'):summary['monthly_contribution']=total['contribution']/months
    if can_result:
        summary['result']=sum((r['result'] for r in rows),ZERO)
        summary['monthly_result']=summary['result']/months
        summary['average_result']=summary['result']/len(rows)
        summary['provisional']=any(r['provisional'] for r in rows)
    current_start = max(month_start(as_of),cutover)
    current = sales(current_start,as_of,channel)
    prev_start = month_start(as_of,-1)
    prev_end = month_end(prev_start)
    prev_cut = prev_start.replace(day=min(as_of.day,prev_end.day))
    if prev_end >= cutover:
        prev_full = sales(max(prev_start,cutover),prev_end,channel)
        prev_part = sales(max(prev_start,cutover),prev_cut,channel) if prev_cut >= cutover else selectors.metrics({})
    else:
        prev_full = prev_part = selectors.metrics({})
    projection = estimate(current,prev_full,prev_part,as_of=as_of,cutover=cutover)
    if projection['available']:
        projected = projection.pop('values')
        projection['values'] = metrics_for(actor,projected)
        if can_result:
            # Preserve the full month's already-recorded non-sales DRE components.
            dre = selectors.dre(dict(start=current_start,end=month_end(as_of)))
            charges = dre['sales']['contribution']-dre['result']
            projection.update(result=projected['contribution']-charges, recorded_charges=charges,
                              provisional=dre['provisional'])
    # Do not put unauthorized values in the HTTP/template context.
    for row in rows:
        row['full'] = metrics_for(actor,row['full'])
        if row['comparable'] is not None:row['comparable']=metrics_for(actor,row['comparable'])
    return dict(rows=list(reversed(rows)), summary=summary, start=first, as_of=as_of, grouping=grouping,
                projection=projection, current=metrics_for(actor,current),
                previous=metrics_for(actor,prev_part) if prev_start >= cutover else None,
                difference=current['revenue']-prev_part['revenue'] if prev_start >= cutover else None,
                change=variation(current['revenue'],prev_part['revenue']) if prev_start >= cutover and month_start(as_of) >= cutover else None,
                current_start=current_start, previous_start=prev_start, previous_end=prev_cut,
                month_end=month_end(as_of), channel=channel, can_result=can_result)
