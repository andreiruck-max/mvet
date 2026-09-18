# Bling — avaliação de integração

Consulta pública em 18/09/2026. **Estudo, não integração ativada.** Não foram solicitadas credenciais nem realizadas chamadas autenticadas na conta da empresa. Contratos e exemplos foram examinados na [referência oficial interativa](https://developer.bling.com.br/referencia), que publica seu OpenAPI. Exemplos não garantem preenchimento dos campos na conta Mercadovet.

## Decisão de produto: importação assistida e independente

O Bling fornece dados para facilitar o preenchimento. O MVet mantém seu próprio estoque, custo médio, CMV, deduções e resultados. Não há sincronização bidirecional nem dependência do Bling para continuar os lançamentos manuais. Decisão detalhada no [ADR 0015](adr/0015-bling-independent-import.md).

A interface prevista é uma área separada **Notas do Bling para conferir**, com estados pendente, em conferência, importada, ignorada e com erro. A situação fiscal recebida do Bling é um campo separado do estado da importação e do status da venda MVet. A consulta não confirma vendas.

O custo médio, custo unitário, CMV ou lucro informados pelo Bling **nunca alimentam o custo da venda ou sobrescrevem o estoque do MVet**. Na confirmação local, os serviços do MVet calculam o CMV com seu próprio custo médio e gravam o snapshot. Valores mostrados na prévia são indicativos: estoque e custo devem ser revalidados na transação de confirmação. Isso não autoriza reconstruir custo histórico de notas antigas com o custo atual.

Após a importação, uma nova consulta não sobrescreve deduções manuais, canal, local de estoque nem snapshots. Divergências externas ficam registradas para conferência.

## Recursos confirmados e aplicação proposta

| Informação | Recurso observado | Aplicação no MVet |
|---|---|---|
| Notas fiscais | GET `/nfe` e `/nfe/{idNotaFiscal}` | Buscar notas e preparar venda para conferência |
| Número, série, data, chave | `numero`, `serie`, `dataEmissao`, `chaveAcesso` | Referência fiscal e detecção de duplicidade |
| Produtos da NF | `itens[].codigo`, descrição, quantidade, unidade e valores | Vincular por SKU, validar unidade/kit e preencher itens |
| Origem comercial | `loja.id`, `numeroPedidoLoja` | Sugerir canal mediante vínculo explícito; permitir conferência |
| Documentos | XML e links de DANFE/PDF no detalhe | Referência para conferência; não emissão fiscal pelo MVet |
| Contas financeiras | GET `/contas-contabeis` e detalhe por ID | Relacionar conta externa à conta MVet |
| Caixa e bancos | GET `/caixas`, detalhe por ID | Movimentos, conta, data, valor, débito/crédito e origem |
| Catálogos adicionais | Grupos Produtos, Depósitos, Estoques, Contatos, Pedidos, Contas a Pagar/Receber | Próximos contratos a homologar, não prometer equivalência de todos os campos |

A tabela resume nomes de campos e recursos observados na referência; não replica payloads, dados reais ou credenciais. Outros detalhes do contrato precisam de homologação específica antes de implementação.

## Fluxo prioritário: NF → venda em revisão

1. Consulta paginada por período explícito, seguida do detalhe da nota.
2. Guardar em área de importação com ID externo, empresa, chave e versão/hash. Vincular eventual pedido à mesma venda: pedido e NF não são duas receitas.
3. Admitir somente documentos compatíveis com venda autorizada. Notas de entrada, devolução, transferência, remessa, complementares ou canceladas não viram vendas normais automaticamente; validar tipo, finalidade e situação.
4. Relacionar SKU exato e vínculo persistente de produto externo. SKU inexistente, duplicado, vazio ou unidade divergente bloqueiam a confirmação; não criar produto/custo silenciosamente. Kits e fracionamentos exigem composição/unidade compatível. Quando o código externo não for o SKU interno, permitir um vínculo explícito aprovado pelo operador; não associar automaticamente por semelhança de nome.
5. Preencher NF/série/data/itens e propor valores. Valor da nota não deve ser equiparado sem reconciliação a valor dos produtos: frete, descontos e tributos podem estar incluídos. Conferir totais com pedido/XML quando necessário.
6. Sugerir canal por `loja.id` mapeado; usuário confirma ou altera. Estoque padrão físico continua selecionável, inclusive Full. Canal Mercado Livre sozinho não identifica se a venda é Full.
7. Operador informa/confere deduções: frete efetivamente pago, taxa do canal, MDR, antecipação, DIFAL, comissão e outros. Campo ausente é **não informado**, não zero confirmado. Imposto fiscal do item não substitui automaticamente a regra gerencial do Simples.
8. Só confirmar após completar pendências; usar os serviços existentes para CMV histórico, baixa de estoque e recebível. Prévia não movimenta estoque nem caixa.

Resultado esperado: normalmente não redigitar número, SKU e quantidades; preencher/conferir deduções e canal. Não é promessa de importar qualquer NF sem exceções. Impedir duplicação também contra vendas lançadas manualmente (NF/série/emitente e chave, além de ID externo).

## Cancelamentos e reconsultas

- Cancelar uma venda no MVet executa somente as reversões locais previstas pelos serviços de vendas/financeiro. Não envia cancelamento ao Bling, não altera a NF externa e não depende da disponibilidade do Bling.
- A interface deve informar claramente que o cancelamento é local e que a situação da nota no Bling permanece independente.
- Cancelamento ou alteração detectados no Bling geram uma divergência para análise humana. Não cancelam, estornam nem apagam automaticamente a venda no MVet.
- Preservar o vínculo de origem mesmo quando a venda local for cancelada ou a nota for ignorada. Reconsultar a mesma NF não cria outra venda, não reativa a cancelada e não refaz a baixa de estoque.
- Reabrir uma conferência ignorada exige ação explícita e auditada. Uma venda cancelada não pode ser reativada pela integração; qualquer correção segue as regras locais e a verificação de duplicidade.
- Preservar corte de 15/09/2026. Nota antiga não autoriza reconstruir CMV histórico com custo atual.

## Saldos bancários: limite e desenho correto

O detalhe público de conta financeira examinado apresenta identificação, descrição, tipo e integração, **não um saldo diário pronto**. `/caixas` lista movimentos filtráveis por conta e datas, incluindo situação de conciliação e registros excluídos. Não foi confirmado endpoint que entregue saldo bancário efetivo de todas as instituições. Não inventar `/contas-financeiras/saldos`.

É viável projetar rotina diária de consulta de movimentos do Bling e derivar posição: saldo inicial conciliado + créditos − débitos. Isso será saldo **segundo os registros do Bling**, não confirmação direta do banco. Lacunas, lançamentos retroativos/excluídos, transferências e retenções precisam ser conciliados. Saldo inicial não pode ser recriado diariamente.

Lançamentos financeiros importados também passam por conferência própria; consultar o Bling não liquida automaticamente títulos do MVet. Manter no MVet separadamente: saldo do livro próprio; posição externa, fonte e instante da consulta; divergência e estado de conciliação. Diferença não gera receita, despesa ou ajuste automático. Movimentos externos de pagamentos já existentes devem ser vinculados, não duplicados. Transferências exigem identificar ambas as pernas; falta de correspondência fica pendente.

Para saldo disponível real, limites, bloqueios, aplicações e valores a liberar, avaliar API bancária/Open Finance ou extrato bancário apropriado. O escopo do Bling por si só não garante esses dados. Homologar uma conta por vez e não chamar saldo contábil de saldo disponível.

## Arquitetura e segurança propostas

Adaptador separado em integrations; estágios de consulta, validação, prévia, aprovação e aplicação pelos serviços de domínio. Unicidade por conexão/empresa + recurso + ID externo, incluindo eventos. Não usar nome do banco/canal como identificador estável. Não registrar tokens nem documentos completos em logs ou GitHub público.

Para rede interna, priorizar polling de saída no servidor da empresa. O servidor precisa permanecer ligado e conectado; mostrar última execução, falhas e defasagem, sem fingir dados atualizados. Webhooks exigiriam receptor alcançável pelo Bling e desenho adicional de segurança; não abrir o ERP ou PostgreSQL à internet para recebê-los.

OAuth2 com escopos mínimos, redirect validado e `state`, segredos locais protegidos e refresh serializado. Alterações de escopos podem exigir nova autorização. [Cadastro e autorização de aplicativos](https://developer.bling.com.br/aplicativos).

Adotar JWT, `enable-jwt: 1` na emissão/renovação e requisições autenticadas, armazenamento de token sem limite curto e Bearer. Tokens opacos estão descontinuados; a página não fixa data de bloqueio. [Guia JWT](https://developer.bling.com.br/migracao-jwt).

Limites por conta: 3 requisições/segundo, 120 mil/dia; filtros temporais de GET não devem exceder um ano. Tratar 429 com espera progressiva e jitter, respeitar outras integrações e não renovar token em paralelo: `/oauth/token` tem limite próprio por IP. [Limites oficiais](https://developer.bling.com.br/limites).

Webhooks, se adotados: validar HMAC SHA256 do corpo original, empresa e evento; persistir antes de responder 2xx em até 5 segundos, tratar repetição e desordem. As retentativas podem durar três dias e falha persistente desabilita a configuração. Estoque físico e virtual/reservado são distintos. [Webhooks oficiais](https://developer.bling.com.br/webhooks).

## Autorizações para a futura integração

Separar: administrar conexão (master), consultar prévia comercial, mapear SKU/canal/depósito, completar deduções, aprovar lote comercial, consultar prévia financeira, conciliar movimentos, aprovar efeitos financeiros, consultar falhas e reprocessar. Cada aprovação também exige autorização da operação de destino. Credenciais e payloads financeiros não ficam visíveis a vendedor. Essas capacidades são especificação futura: não exibir permissões fictícias antes de haver endpoints correspondentes.

## Critérios de homologação antes de ativar

- Aplicativo autorizado pela empresa com leitura mínima; confirmar plano/escopos disponíveis. Nunca enviar secret/token no chat.
- Amostras privadas de venda normal, Full, kit, desconto, frete, cancelamento e NF sem SKU.
- Reexecução do mesmo lote, pedido + NF e NF previamente manual não duplicam estoque, receita ou recebível.
- Comparação com notas, vendas e bancos em período fechado; dados faltantes ficam pendentes.
- Simular falha de rede, paginação incompleta, 401/429, token revogado e alteração retroativa.
- Estoque externo inicialmente somente comparação; não conciliar baixas importadas com ajustes automáticos de saldo simultâneos.
- Piloto somente leitura, depois aprovação assistida de vendas, depois conciliação financeira. Escrita no Bling não faz parte da integração definida; qualquer proposta futura exige nova decisão explícita.

## Aceite específico da independência

Na implementação, testes devem demonstrar:
- Custo incorreto recebido do Bling não afeta o CMV calculado pelo MVet.
- Nota pendente não altera estoque, caixa ou resultado confirmado.
- Confirmação usa o custo local vigente na operação, sem alterar snapshots anteriores.
- Cancelamento local não realiza chamadas de alteração ao Bling.
- Reconsulta após cancelamento local não duplica nem reativa a venda.
- Alteração/cancelamento externo gera divergência, preservando a operação local até decisão autorizada.
- Deduções, canal e estoque escolhidos pelo usuário não são sobrescritos por nova consulta.
- Código externo sem vínculo inequívoco bloqueia a confirmação.
- Operações manuais continuam disponíveis quando a integração estiver indisponível.

Esses critérios especificam trabalho futuro; a fila, o adaptador e esses testes ainda não foram implementados.
