# Regras de negócio
## Cadastros e histórico
SKU único. Cadastros com histórico são inativados. Transações não são apagadas. Cancelamento e estorno conservam origem, motivo, ator e horários. Número/série da NF impedem duplicidade acidental; rascunho não movimenta estoque.

## Estoque
Livro de movimentos obrigatório. Custo médio global = valor global / quantidade global. Quantidade por local. Entrada pondera custo; última saída absorve resíduo de arredondamento. Não permitir saldo negativo. Transferência conserva patrimônio; fracionamento transfere custo ao resultado. Kit virtual baixa componentes e congela custo real consumido; kit sem composição é inválido. Alteração futura da composição não muda cancelamento antigo.

## Venda
Receita operacional = produtos − desconto + frete recebido.
Margem de contribuição = receita operacional − CMV − frete pago − taxas − imposto − DIFAL − comissão − outros custos variáveis − taxas extras.
Percentual = margem / receita operacional, indefinido quando receita zero.
CMV congelado na confirmação. Imposto exige vigência, base e snapshot; override com motivo auditado. Margem de venda não é EBITDA.

## Compras e financeiro
Compra e parcelas são entidades separadas. Recebimento físico gera estoque uma única vez; custos acessórios rateados com preservação do total. Pagamento idempotente cria liquidação e débito, nunca duas liquidações no duplo clique.
Transferência não é receita/despesa e consolida zero. Saldo realizado considera somente realizado até a data. Projetado inclui previstos/títulos em aberto sem duplicar liquidações.
Despesas entram por competência. Compra de estoque somente vira CMV na venda. Principal de empréstimo reduz dívida; juros são resultado financeiro.

## Corte
15/09/2026. Entrada manual. Abertura é saldo antes das operações do dia, fora da DRE. Títulos legados abertos sem novo reconhecimento de resultado. Sem reexecução automática de vendas anteriores sobre o saldo de abertura.
Data efetiva e data de registro são distintas. Correção de estoque não pode revalorizar silenciosamente vendas antigas.

## Autorização
Permissão de lançamento não concede indicadores consolidados, custo, margem, DRE ou bancos. Backend, APIs e busca respeitam autorização. Alertas não bloqueiam operações válidas; integridade pode bloquear.

## Implementação
Este documento define contratos do produto. Consulte BACKLOG para saber quais estão implementados e testados.

## Alterações autorizadas em 16/09/2026
- Estoque padrão físico configurável por empresa e alterável em cada venda; cadastros adicionais livres, saldo separado por local.
- Edição de alíquota com início anterior a hoje recalcula vendas confirmadas abrangidas e mantém revisões imutáveis/auditoria. Início hoje/futuro preserva as já confirmadas. CMV e estoque nunca recalculados por imposto. Overrides manuais/canceladas preservados. Ver ADR 0009.
- Taxas extras nome/valor (ex.: MDR) deduzidas da contribuição uma única vez.
