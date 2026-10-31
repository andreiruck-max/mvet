# ADR 0040 — Interface comum e apresentação dos PDFs

Aceito em 12/10/2026, a pedido do proprietário.

## Problema
Controles e navegação cresceram com estilos inconsistentes. PDFs com colunas iguais e fontes dependentes do leitor dificultavam conferir valores e notas longas.

## Decisão
Separar a camada visual comum dos layouts de domínio. Usar tokens claros/escuros, ações reconhecíveis, busca local dos destinos já autorizados e indicação do módulo atual. Preservar a matriz de caixa aprovada e suas semânticas financeiras.

PDFs recebem um conjunto de estilos comum, fontes incorporadas do ReportLab, proporções por conteúdo e cabeçalhos repetidos. Vendas continuam separadas por canal; caixa é dividido em grupos de três dias. Notas extensas podem continuar em páginas subsequentes sem truncar produtos. Nenhum modelo, cálculo, permissão ou lançamento é alterado; não há migration.

## Validação
Suíte funcional, exportação de notas extensas e matriz projetada; navegador em desktop/celular, navegação e temas; renderização de PDFs sintéticos para revisão de alinhamento, fontes, quebra de página e valores negativos.

## Revisão de apresentação — 31/10/2026

Seções curtas compartilham a página disponível; agrupamentos de canais, depósitos e três dias do caixa permanecem identificados, sem quebra obrigatória. Títulos ficam com cabeçalho e primeira linha, permitindo que o restante da tabela continue. Menos espaçamento vertical, mantendo fonte de corpo e valores em 8,5 pt. Comissões compactam termos em duas linhas e levam os critérios ao final; um novo comissionado começa em página própria. Nenhum dado é truncado para caber em uma página.
