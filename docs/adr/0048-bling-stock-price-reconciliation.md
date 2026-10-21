# ADR 0048 — Conferência bidirecional de preço e saldo com Bling

Decisão de 20/10/2026, solicitada pelo master. Amplia o adaptador da ADR 0015: leitura de produtos/depósitos/saldos, PATCH apenas do preço de produto e POST apenas de balanço de estoque. Escritas fiscais, financeiras, alteração de custos e sincronização automática permanecem proibidas.

## Identidade e comparação

SKU exato e único entre produtos ativos do Bling, unidades coincidentes e produto simples ativo. Detalhe externo precisa confirmar ID/SKU. Não inferir vínculo por descrição nem converter unidades. Produtos compostos/pais de variação ficam bloqueados. Depósitos são escolhidos explicitamente, sem mapear apenas pelo nome. Ausência de saldo não é zero. Compara saldo físico do depósito e preço do cadastro Bling com o preço de venda da loja MVet (não preço de marketplace).

## Correção explícita

Master escolhe campo (preço/saldo) e destino (MVet/Bling), informa motivo e confirma prévia assinada. Nova leitura antes de aplicar rejeita dados alterados. Cada prévia serve uma única correção. Registra intenção durável antes de escrever no Bling; nunca repete tentativa com resultado incerto, mesmo com nova prévia do produto. Histórico permite registrar conferência manual após cinco minutos para encerrar tentativa desconhecida. O encerramento não afirma sucesso automático. Resposta confirmada exige releitura do valor enviado. Não há transação distribuída: alterações externas concorrentes no intervalo entre leitura e escrita são possíveis; não prometer atomicidade entre sistemas.

Preço fixo opcional do produto prevalece sobre markup. Importar preço não modifica custo nem vendas históricas. Apagar o preço fixo em Editar preço restaura o cálculo por custo × markup. Preços previamente calculados permanecem iguais após migration (NULL).

Saldo local usa serviço de contagem e livro imutável, na data atual e com custo local. Bloqueia acréscimo sem custo de referência, saldo negativo como alvo e prévia vencida. Saldo Bling usa operação B (balanço), depósito e produto explícitos, sem enviar custo/preço unitário do estoque. O usuário é informado de possíveis efeitos nas integrações de canais do Bling.

## Cadastro a partir do Bling

Busca paginada no catálogo externo; prévia copia SKU/unidade/nome/preço de produto simples. Nome e preço são revisáveis. Cadastro não duplica SKU existente (inclusive inativo) ou ID externo já importado por esse fluxo. Estoque zero por padrão. Importar saldo é escolha explícita, exige saldo não negativo e custo positivo informado manualmente para saldo positivo. Cria cadastro, preço fixo e ajuste de entrada atomicamente, com chave de repetição e auditoria. Não importa custo médio externo. Não altera NF, contas ou vendas.

## Verificação

Testes sintéticos para os dois sentidos/campos, CMV, identidade/unidade, saldo ausente, prévia vencida/adulterada, permissão, replay e resposta remota perdida, cadastro sem/com estoque. Aceitação Chromium cobre prévia/confirmação e cadastro. Credenciais e dados reais não são versionados; homologação com conta real ocorre no ambiente do usuário.

## Revisão de 21/10/2026 — consulta persistida e precisão externa

Autorizada pelo usuário: guardar a última página por master em BlingComparisonCache, sem expiração temporal. Filtro e retorno reaproveitam a consulta; outra página ou botão de consulta fazem leitura explícita. Snapshot assinado da comparação deixa de expirar em 30 minutos; aprovação da gravação continua válida por 10 minutos e cada aplicação revalida identidade, depósito, preço e saldo locais/remotos. Replay e resultado incerto continuam protegidos. Cache não autoriza escrita nem substitui as verificações.

Valores válidos do Bling são normalizados com Decimal e ROUND_HALF_UP para 2 casas de preço e 4 de quantidade. Ausentes, não finitos e fora do limite não são zero. Saldo inválido bloqueia o produto sem derrubar a página. Consulta e prévia usam a mesma precisão; UI informa o arredondamento. Não há alteração de CMV ou custo histórico.
