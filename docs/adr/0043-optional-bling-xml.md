# ADR 0043 — XML opcional na conferência do Bling

Data: 15/10/2026. Status: aceito.

A indisponibilidade do XML complementar não deve impedir importar uma nota cujo detalhe JSON é válido. O XML serve exclusivamente ao pré-preenchimento de descontos.

Falhas de download, URL não permitida ou XML inválido retornam o detalhe sem descontos extraídos. Não inferir descontos pela diferença de totais. A tela informa a ausência de conferência e permite preencher descontos manualmente. Desconto explícito zero validado continua distinto de desconto desconhecido.

Preservar limites, restrições de URL, ausência de credenciais e bloqueio de redirecionamentos. Validações fiscais do JSON, permissões e confirmação local permanecem obrigatórias. A consulta não confirma vendas/compras nem altera estoque. Snapshots aprovados e escolhas locais permanecem preservados.
