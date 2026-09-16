# Financeiro — contrato para Fases 4–6
Estado: especificado, módulos financeiros ainda não implementados.

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

## Atualização Fase 4
Compras e PurchaseInstallment já implementados. Obrigações de compras ORDERED/RECEIVED, com status PENDING, são compromissos válidos; rascunhos/canceladas não compõem pendências. A Fase 5 deve vincular essas parcelas à liquidação/título sem duplicação, manter valor principal e tratar diferenças/juros/descontos explicitamente. Atualizar proteção PostgreSQL para transições financeiras legítimas e bloquear cancelamento de compra com liquidação não estornada. Não há pagamento simulado nesta fase.
