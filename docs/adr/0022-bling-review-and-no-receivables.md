# ADR 0022 — Conferência compacta e vendas sem recebíveis

Aceito em 25/09/2026 por solicitação do usuário.

Novas vendas, manuais ou provenientes do Bling, não geram títulos a receber. Não excluir nem migrar títulos históricos; cancelamento de origem mantém guarda de liquidações. Estoque, custos, impostos, DRE e relatórios continuam independentes da existência de recebíveis. Compras e despesas mantêm suas contas a pagar.

A configuração master define uma referência Full com canal/estoque e um destino padrão para todas as demais referências, inclusive ausentes. Persistir FKs, não inferir por nomes nem fixar dados da empresa no código. Valores sugeridos apenas no formulário inicial; POST manual prevalece. Canais/locais inativos não são selecionados.

A confirmação pelo botão substitui a caixa genérica de revisão. A declaração específica de finalidade ausente permanece obrigatória. Campos de imposto manual não são oferecidos na conferência; exigir regra tributária e ignorar tentativas de sobrescrita via POST. Serviços de vendas manuais permanecem com suas regras próprias.

Deduções iniciam em zero, editáveis. Frete recebido e pago recebem a mesma sugestão valorFrete por decisão expressa do usuário; o valor pago é estimativa a conferir, não custo certificado pelo Bling. Desconto não é inferido por diferença fiscal: o contrato GET NF-e consultado não documenta desconto (campo writeOnly no DTO POST). Campo manual inicia em zero. Alvo opcional de receita mantém vazio com indicação 0,00 para não zerar receita inadvertidamente.

Fonte consultada: OpenAPI oficial Bling, NotasFiscaisDadosGetDTO/NotasFiscaisDadosPostDTO, em 25/09/2026. Nenhum payload comercial versionado. Migração cria somente a tabela de sugestões, sem reescrever vendas ou notas.
