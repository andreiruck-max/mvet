# ADR 0038 — Posição de estoque, preço da loja e caixa futuro

## Decisão autorizada
Preço de venda somente na loja Mercadovet: custo médio local × (1 + markup/100), arredondamento HALF_UP em centavos. Padrão inicial 35%, geral ou exceção individual (nulo herda; zero explícito válido). Somente master configura. O Full não recebe essa precificação. Valores são sugestões atuais: nenhuma venda histórica ou rascunho é reprecificado. Custos continuam protegidos por capability; a carteira operacional sem view_costs recebe apenas quantidade/preço em HTML, consulta e exportação.

A loja é identificada pelo cadastro ativo Estoque Mercadovet/Mercadovet; se não existir, usa o depósito padrão ativo, desde que não seja Full. Não inferir preço pelo custo consolidado dos dois depósitos.

## Conciliação de base
Arquivo privado versionado 2 com posições por SKU/local, quantidade, custo e valor. Não versionar dados da empresa. Apenas master pode enviar, conferir e aplicar. Prévia inclui alterações, produtos novos, posições ausentes zeradas e movimentos posteriores. Flag complete explícita: ausentes têm quantidade/valor zero NA BASE, nunca são apagados. Unidade/nome existentes preservados; novos produtos usam os dados do arquivo.

Posição alvo atual = posição na base + soma dos movimentos posteriores à base. A diferença para a projeção vigente é registrada por RECONCILE na data atual. Livro, vendas, CMV, entradas/saídas posteriores e financeiro são preservados. Ao esgotar totalmente uma posição, qualquer valor residual é absorvido pelo ajuste de valorização e exposto na prévia; sinais incompatíveis são bloqueados para conferência. Não registrar essa correção de referência como receita de venda ou obrigação financeira. Custo de referência de quantidade zero vem da base.

Digest canônico evita replay; uma data-base aceita uma conciliação (corrigir novamente exige nova base/contagem). Revisão da prévia considera livro, projeções e cadastros sob mutex de domínio. Mudança concorrente invalida confirmação. Todos os depósitos são aplicados atomicamente. Relatório imutável por modelo e trigger PostgreSQL, operações e movimentos também imutáveis. Conciliação não tem estorno genérico: ajuste por contagem/custo ou nova base.

Limite deliberado: notas históricas lançadas APÓS a conciliação, com data anterior/igual à base, continuam sendo novos movimentos do ERP. A conciliação não pode adivinhar se já estavam no arquivo. Finalizar lançamentos da base antes de aplicar. Ajustes não corrigem CMV de vendas passadas; correções comerciais usam o fluxo auditado próprio.

## Caixa
Padrão hoje até hoje+15 (16 datas inclusivas), dia atual destacado. Crédito/débito manual aceita data futura usando o mesmo título/liquidação da ADR0037: reserva principal, aparece uma vez na projeção, só entra no realizado na data; estorno antecipado reabre título sem caixa antecipado. Não se confunde com autorização de movimento físico futuro.
