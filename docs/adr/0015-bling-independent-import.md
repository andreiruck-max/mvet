# ADR 0015 — Bling como fonte de preenchimento independente

Data: 18/09/2026. Status: aceito; implementação da importação assistida de NF, com homologação real pendente.

## Contexto

A empresa deseja reduzir a digitação de notas e itens, completar manualmente custos de marketplace e controlar estoque e custo médio no MVet. O custo do Bling não é a fonte de verdade para a gestão local. Cancelamentos precisam ser independentes.

## Decisão

Importar notas para uma fila separada de conferência. Aproveitar referências fiscais, produtos vinculados por SKU/código externo, quantidades e valores conferidos. O operador completa deduções, confirma canal e escolhe o estoque. Apenas a confirmação pelos serviços locais produz efeitos transacionais.

O MVet calcula o CMV exclusivamente pelo próprio custo médio e mantém snapshots. Não importar custos ou saldos externos para sobrescrever o livro local. Prévia não garante custo histórico para uma nota antiga.

Não enviar alterações operacionais ao Bling. Cancelamento local não cancela documento externo; mudança externa gera divergência para decisão humana, sem reversão automática. A indisponibilidade do Bling não impede lançamentos manuais.

Preservar identificadores e vínculos externos após cancelamento/ignorar, garantindo idempotência sem reativação automática. Uma reconsulta não sobrescreve escolhas manuais nem dados históricos. Lançamentos financeiros externos exigem conciliação própria para não duplicar títulos ou liquidações.

## Consequências

A integração reduz digitação, mas mantém uma etapa humana de conferência. Situação fiscal externa, estado de importação e status da venda local precisam ser distintos na interface e no modelo. Divergências entre sistemas são esperadas e rastreáveis.

Identificadores externos servem à rastreabilidade e prevenção de duplicidade, sem impor sincronização dos ciclos de vida. Sincronização de escrita exigiria outra decisão explícita.

Fluxos, permissões e critérios de aceite: [BLING_INTEGRATION.md](../BLING_INTEGRATION.md).
