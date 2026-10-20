"""Supplier quotation files from the same filtered replenishment calculation."""
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone
from apps.core.models import Company
from apps.core.services import require, audit
from apps.reporting.datasets import Dataset
from apps.reporting.files import xlsx, pdf


def export_plan(request, rows, values):
    require(request.user, 'core.export_purchases')
    file_format = request.GET.get('export')
    if file_format not in ('xlsx', 'pdf'):
        raise ValidationError('Formato de exportação inválido.')
    scope = request.GET.get('scope', 'filtered')
    if scope not in ('filtered', 'selected'):
        raise ValidationError('Selecione todos os filtrados ou os itens marcados.')
    if scope == 'selected':
        try:
            ids = {int(value) for value in request.GET.getlist('product')}
        except ValueError:
            raise ValidationError('Seleção de produtos inválida.')
        if not ids:
            raise ValidationError('Marque os produtos que deseja enviar ao fornecedor.')
        eligible = {row['product'].pk for row in rows}
        if not ids <= eligible:
            raise ValidationError('A seleção não corresponde aos filtros atuais. Reabra o planejamento e selecione novamente.')
        rows = [row for row in rows if row['product'].pk in ids]
    limit = 2000 if file_format == 'pdf' else 10000
    if not rows:
        raise ValidationError('Nenhum produto para exportar com estes filtros.')
    if len(rows) > limit:
        raise ValidationError(f'Limite de {limit} produtos. Reduza os filtros; nenhum produto foi omitido.')
    today = timezone.localdate()
    dataset = Dataset('Solicitação de cotação',
        ['SKU', 'Produto', 'Unidade', 'Quantidade sugerida'],
        [[r['product'].sku, r['product'].name, r['product'].unit, r['suggested']] for r in rows],
        f'Emissão: {today:%d/%m/%Y} · Depósito: {values["location"]}. '
        f'Histórico: {values["history_days"]} dias · Cobertura: {values["coverage_days"]} dias. '
        'Quantidades sugeridas para conferência de embalagem e disponibilidade. Não constitui pedido confirmado.')
    company = Company.objects.get(pk=1)
    if file_format == 'pdf':
        # The shared PDF currency formatter uses two decimals; quantities need four.
        for row in dataset.rows:
            row[3] = f'{row[3]:,.4f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    content = xlsx(dataset, company.name) if file_format == 'xlsx' else pdf(dataset, company.name)
    audit(request.user, company, 'export_report', after={
        'report': 'purchase_planning', 'format': file_format, 'rows': len(rows),
        'filters': dict(request.GET.lists()), 'scope': scope})
    response = HttpResponse(content, content_type='application/pdf' if file_format == 'pdf'
                            else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="mvet-cotacao-{today.isoformat()}.{file_format}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
