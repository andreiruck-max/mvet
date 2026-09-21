# ADR 0017 — Finalidade ausente na consulta Bling

Data: 21/09/2026. Status: aceito.

## Evidência
Na homologação real, GET /nfe/{id} retornou situação 5, tipo 1 e itens P com CFOP 6108, mas omitiu finalidade e retornou tipoNota vazio. O fixture inicial assumia finalidade presente e não representava esse contrato. Os valores comerciais reais não são versionados.

## Decisão
Ausência de finalidade não equivale a finalidade normal. Notas sem esse campo entram na fila, ainda sujeitas à situação autorizada, saída, CFOP conservador de venda, identidade fiscal, SKU e unidade. Antes da confirmação, o usuário autorizado deve conferir o documento no Bling/DANFE e marcar declaração específica de venda com finalidade normal, não devolução/complemento/ajuste/remessa. A declaração é obrigatória inclusive para master e validada no serviço, sem valor padrão verdadeiro.

Finalidade conhecida diferente de normal permanece bloqueada. tipoNota não é usado como substituto por não haver equivalência comprovada. O MVet não baixa XML automaticamente e não infere finalidade pelo CFOP.

A finalidade externa continua vazia no snapshot. O log bling_approve registra purpose_missing e purpose_reviewed, além do usuário, data e referência existentes. Não há alteração de snapshots antigos nem migration. Reconsultar a mesma nota recupera entradas com o erro anterior sem duplicar registros; ignoradas e vendas vinculadas preservam seu estado.

## Limite
A conferência humana supre a informação ausente; não constitui validação fiscal automática. Uma declaração humana incorreta ainda pode classificar indevidamente um documento. API sem consulta de estoque/custo externo ou escrita no Bling permanece inalterada.
