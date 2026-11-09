"""Terms for commission control only; never creates receivables or receipts."""
from datetime import date
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from apps.inventory.services import number


def normalize_terms(rows, sale_date, face):
    if not isinstance(rows, list) or len(rows) > 60:
        raise ValidationError('Informe no máximo 60 parcelas para comissão.')
    result = []
    for row in rows:
        try:
            due = date.fromisoformat(str(row['due_date']))
            amount = number(Decimal(str(row['amount'])), Decimal('0.01'))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ValidationError('Informe vencimento e valor válidos em cada parcela para comissão.')
        if due < sale_date:
            raise ValidationError('Vencimento da parcela anterior à venda.')
        result.append({'due_date': due.isoformat(), 'amount': format(amount, '.2f')})
    if result and sum((Decimal(r['amount']) for r in result), Decimal('0')) != face:
        raise ValidationError(f'As parcelas para comissão devem somar R$ {face:.2f} (produtos − desconto + frete recebido).')
    return result


def plan_terms(sale):
    face = sale.products_amount - sale.discount + sale.shipping_received
    rows = normalize_terms(sale.commission_installments, sale.date, face)
    return [(date.fromisoformat(r['due_date']), Decimal(r['amount'])) for r in rows] or [(sale.date, face)]
