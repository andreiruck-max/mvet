# Exportações Excel e PDF

Botões nos módulos atuais: faturamento, vendas em tabela, produtos/estoque, compras, compras a pagar, títulos financeiros, fluxo diário, despesas e DRE. Usam os filtros selecionados e abrangem todo o resultado, não apenas a página atual. Não salvam dados em serviço externo.

Excel preserva a organização útil do modelo ERP Mvet(2).xlsx: vendas em linhas, estoque SKU/produto/quantidade/custo/total, compras por parcela, caixa com cada dia ocupando três colunas (entradas, saídas, saldo). Caixa inclui aba detalhada com inicial/final/projetado e aviso de pendências sem conta. Estoque inclui saldos por local. Valores e datas são células tipadas, não textos monetários; texto iniciado por `=` não vira fórmula. NF/SKU permanecem texto.

Não é cópia binária do arquivo original: dados comerciais e fórmulas antigas não são distribuídos. EBITDA/LUCRO de venda passam a denominações de margem corretas. Campos novos ficam à direita; colunas proibidas são removidas, nunca apenas ocultadas. Relatórios são fotografias dos dados na emissão, não planilhas operacionais sincronizadas. Alterar o arquivo exportado não altera o ERP.

PDF tem empresa, filtros, cabeçalhos repetidos e páginas numeradas. Tabelas largas são divididas em blocos com as duas primeiras colunas repetidas, sem diminuir toda a venda até ficar ilegível. Estoques por local aparecem em seção própria. DRE conserva competência e avisos de resultado parcial.

## Segurança e limites

Permissão `export_<módulo>` **e** leitura do relatório são obrigatórias. Custos e margens exigem suas permissões; saldo requer consulta financeira; DRE é acesso sensível completo. Arquivos não contêm colunas ocultas com dados proibidos. Toda emissão registra ator, relatório, formato, filtros e quantidade de linhas na auditoria, sem copiar conteúdo do arquivo.

Exportações: até 10.000 linhas no Excel e 2.000 no PDF; acima disso, resposta explícita pedindo filtros menores. Nunca truncar silenciosamente. Caixa aceita até 366 dias no formulário vigente e 10.000 posições conta/dia. Os arquivos são gerados depois de liberar o mutex transacional, a partir da projeção consistente já materializada.

Saldo inicial e movimentos têm datas próprias; exportação não cria competência, liquidação ou ajuste. Rascunhos/canceladas podem aparecer quando solicitados mas não entram nos totais confirmados. Compra sem parcelas continua visível em Compras; em Compras a pagar aparecem somente parcelas financeiras do filtro.

Revogar acesso impede novas consultas/exportações, mas não recolhe arquivos já baixados. Controle compartilhamento e pastas de downloads nos computadores internos. Backup do banco não deve ser confundido com exportação de relatório.

## Manutenção

`reporting/datasets.py`: projeções autorizadas e filtros. `files.py`: serializers OOXML sem dependência do Excel e PDF ReportLab. `exports.py`: autenticação, limites, download e auditoria. Adicionar campo exige testar autorização em HTML, API, Excel e PDF. Não passar objetos brutos a serializers que possam exportar todos os atributos.
