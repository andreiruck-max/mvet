# Financeiro — Fase 5
Contas, títulos, liquidações, transferências e caixa diário implementados. Evidências de validação no PR da fase. Despesas por competência e DRE permanecem nas Fases 6/7.

## Entidades
Compra é aquisição; parcela é obrigação. Recebimento físico cria estoque. Pagamento só ocorre por liquidação.
FinancialTitle unifica pagar/receber com vínculos para compra, venda ou despesa. Título legado tem flag de abertura e não gera nova competência.
FinancialAccount possui nome, instituição, tipo, saldo/data de abertura, status. Histórico impede exclusão física.
FinancialTransaction guarda conta, data, direção, valor, descrição, categoria, status, ator, origem e reversão.

## Pagamento/recebimento
Data efetiva, conta, valor pago e observação. Lock do título e unicidade da liquidação garantem idempotência. Política para juros/descontos/diferenças deve ser explícita; não zerar saldo pendente silenciosamente.
Cancelar título não é apagar pagamento. Liquidação realizada deve ser estornada antes de cancelar compromisso.

## Caixa
Quadro diário por conta: abertura + créditos − débitos = saldo final. Saldos derivados por consulta; lançamento passado afeta consultas posteriores.
Realizado: apenas valores efetivos até a data. Projetado: inclui compromissos/previstos, sem duplicar títulos liquidados.
Transferência própria cria duas pernas iguais; consolidado zero. Não entra na DRE.
Saldo inicial é abertura do dia. Empréstimo: principal patrimonial e juros financeiros separados.

## Despesas
Competência, vencimento, valor, favorecido, categoria hierárquica, status, conta/pagamento, recorrência. Regras determinísticas configuráveis por prioridade/campo/operador/valor/categoria; correção humana prevalece.
Testes: crédito/débito, transferência conservativa, saldo diário, retroativo, futuro, abertura, título legado, duplo clique e estorno.

## Operação implementada
1. Financeiro → Contas financeiras: cadastre instituição/tipo, saldo e data inicial. Saldo é o do início daquele dia; não relance operações já incluídas nele. Saldo negativo é aceito. Conta utilizada só pode ser inativada e sua abertura fica protegida. Conta nunca utilizada pode ser excluída com confirmação/auditoria.
2. Compras confirmadas geram um título a pagar por parcela, antes do recebimento físico. Vendas confirmadas geram recebível bruto (produtos − desconto + frete recebido). Não crie outro título para a mesma operação.
3. Abra título pela parcela ou por Contas a pagar e receber. Ajuste vencimento e conta prevista. Datas de liberação de marketplaces não são adivinhadas. Sem conta definida, a pendência aparece em alerta fora dos quadros por banco.
4. Marcar como pago / Registrar recebimento solicita conta efetiva, data, principal baixado, juros, desconto, valor efetivo e observação. Pagamento parcial mantém o restante pendente. Reenvio não duplica débito/crédito.
5. Liquidação não é editada nem apagada: estorne com data/motivo e registre corretamente. Estorno reabre principal e preserva original/contraparte nas respectivas datas.

Valor efetivo = principal + juros/acréscimos − desconto/abatimento. Diferenças exigem observação. Abatimento integral pode encerrar principal sem movimento bancário, mantendo histórico. Retenção de marketplace pode ser abatimento identificado no recebível bruto; não altera margem da venda nem deve gerar outra taxa na DRE. Conciliação por tipo de retenção evoluirá nas próximas fases. Imposto da venda não gera pagamento automático.

## Manuais e abertura
Novo título registra crédito/débito previsto; liquidar registra o realizado. Datas futuras são apenas previstas. Data real respeita corte, origem e abertura da conta. Pendência anterior ao corte exige origem anterior a 15/09/2026 e flag de abertura; não gera nova competência. Principal de dívida e juros devem usar títulos/classificações distintos: patrimonial e financeiro.
Principal/origem do título são imutáveis: para corrigir valor, estorne liquidações, cancele e recrie. Vencimento, conta e observação podem mudar com auditoria/revisão otimista. Uma venda tem um título agregado com pagamentos parciais e previsão do saldo restante; cronograma com parcelas de venda em vencimentos distintos é evolução posterior.

## Previsões e consultas
Fluxo limitado a 62 dias por consulta. Realizado inclui original e estorno com efeito nas próprias datas; datas futuras mantêm o realizado atual. Projetado soma realizado, principal restante dos títulos e transferências previstas, sem duplicação. Títulos/previsões vencidos são carregados para hoje; o passado não recebe pendências atuais fictícias. Títulos sem conta são informados em alerta separado até a data final, inclusive quando filtrando um banco. Contas inativas preservam histórico e previsões, mas não recebem novas liquidações.
Transferência prevista pode ser realizada na data efetiva ou cancelada. Alterar valor/contas exige cancelar e refazer. Transferência realizada exige estorno integral. Não confundir transferência financeira com transferência física Mercadovet ↔ Full.

## Integração e proteção
Migração cria títulos de compras/vendas já confirmadas, sem gerar dinheiro. Cancelar origem exige primeiro estornar liquidações ativas. PurchaseInstallment preserva valor/vencimento contratual; situação/pagamentos derivam do título. Relatório do fornecedor soma somente o principal restante.
`operate_finance` permite operar sem conceder saldos consolidados. `view_finance` permite caixa/contas/API. Administração de contas exige ambas. Usuário de vendas não ganha acesso financeiro pelos vínculos automáticos. Não há admin transacional.
Lock compartilhado, UUID/fingerprint normalizado, revisão otimista, constraints e triggers protegem histórico e transferências equilibradas. Categorias básicas do caixa não substituem plano de contas/competência. Ver ADR 0011, testes e guias de implantação/backup.
# Integração com despesas (Fase 6)
Expense cria um FinancialTitle a pagar com source=expense, sem débito bancário. Liquidação e estorno usam o livro existente. Cancelar pelo módulo de despesas exige pagamentos estornados e cancela também a obrigação; cancelamento direto do título é bloqueado. Competência e plano histórico pertencem à despesa, não ao título nem à data do pagamento. Recorrência cria obrigações futuras sem caixa. Ver docs/EXPENSES.md.
