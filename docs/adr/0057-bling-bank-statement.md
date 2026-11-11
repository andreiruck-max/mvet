# ADR 0057 — Extrato Bling persistido e comparação líquida

11/11/2026. Aprovado pelo pedido do usuário; preparado fora da main.

## Contrato
Referência pública interativa Bling consultada em 11/11/2026 (OpenAPI `openapi-CR5QY_N1.json`). GET `/contas-contabeis` lista contas; detalhe não fornece saldo. GET `/caixas` filtra `idContaFinanceira`, `dataInicial`, `dataFinal`, `pagina`, `situacaoConciliacao=3`, `situacao=R/E`. Os movimentos contêm id, data, valor, debCred D/C, situação R/E, descrição, observações, conta, contato e origem. Não usar `limite` para `/caixas`: não consta no contrato consultado. Paginar até lista vazia. Contrato público não substitui homologação com os escopos financeiros da instalação.

## Decisão
- Vínculo explícito, único por conta externa e conta MVet; master configura. Vínculo não troca de conta depois de salvo. Saldo externo de abertura opcional, informado antes dos movimentos da data inicial. Ausência não vira zero. Alteração do saldo de referência é auditada e não altera livro MVet.
- Espelho próprio de lançamentos externos, único por vínculo/ID, persistido no PostgreSQL e incluído no backup. Não criar títulos, despesas, estoque, baixas ou operações bancárias. Nenhuma escrita na API financeira.
- Abrir a conta/extrato exibe histórico salvo imediatamente. JS envia POST com CSRF para enfileirar atualização; GET não consulta API nem cria tarefas. A consulta continua no `bling-worker` mesmo fechando a tela. Usuário precisa view_finance e fetch_bling para atualizar; leitura salva exige view_finance; worker revalida acesso antes de cada página.
- Atualizar o dia e cobrir dias desde a última importação, em blocos de até 366 dias; primeira consulta desde a data inicial. Visitas simultâneas reutilizam a tarefa em andamento. Se ela for histórica, encadear a atualização até hoje. Desativar atualização ao abrir não cancela trabalho já solicitado.
- Paginação persistida e lock PostgreSQL contra workers duplicados. Uma página por passagem; consultas fiscais e financeiras compartilham serialização da conexão/token. Falha tenta novamente após 5 minutos, até três falhas consecutivas, preservando páginas e histórico publicado.
- Páginas ficam em staging e só são publicadas após conclusão de R e E. Marcar ausentes/excluídos, sem apagar histórico publicado; não entram no total. Reconsulta por ID atualiza os dados sem duplicar. Páginas repetidas, contas/datas/valores inválidos impedem publicação. Não declarar período completo se a consulta falhar.
- Dias completamente consultados registrados, inclusive sem movimentos. Sem cobertura completa ou abertura, saldo externo é indisponível. Totais comparáveis são líquidos por dia/período, aceitando várias taxas/liberações externas para um lançamento MVet. Diferença = MVet − Bling. Igualdade numérica não é certificação de conciliação individual.
- Consulta manual do período atualiza também correções e exclusões antigas. Atualização do dia não detecta alterações anteriores ao intervalo consultado; datas e última consulta ficam visíveis. Saldo calculado usa o espelho salvo e não confirma saldo disponível no banco. Instantâneos remotos não são transacionais: caso Bling mude durante paginação, reconsultar o período.

## Validação
Testes: publicação atômica, repetição, falha e retomada, exclusão/ausência, cobertura incompleta, agrupamento líquido, permissões/CSRF/revogação, vínculo único, dia atual após importação histórica, previstos/futuros fora da comparação. Navegador: consulta automática ao abrir, histórico disponível durante execução, atualização da tela, persistência e layout desktop/mobile. Homologação real pendente, sem credenciais/dados comerciais no repositório.
