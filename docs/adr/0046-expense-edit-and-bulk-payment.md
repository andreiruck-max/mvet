# ADR 0046 — Edição auditada de despesas e baixa em lote
Data: 16/10/2026. Estado: aceito. Substitui a exigência de cancelar e relançar para corrigir valor/datas da ADR 0012.

## Decisão
Master pode editar os campos comerciais de uma despesa ativa: descrição, valor, competência, documento, fornecedor/favorecido, categoria, centro de custo, observação, recorrência, vencimento e conta prevista. Exige motivo e versões da despesa e do título. ExpenseRevision imutável guarda antes/depois completos dos campos editáveis e o usuário. As revisões anteriores apenas de classificação continuam válidas.

Despesa e obrigação são atualizadas na mesma transação, sob domain_lock. PostgreSQL admite a exceção somente no contexto de uma revisão correspondente ao antes/depois; origem, identificadores, autoria original, status e livro bancário seguem protegidos. Valor deve ser positivo e não inferior ao principal já liquidado; documento não pode ultrapassar pagamento não estornado. Competência/documento respeitam o corte, vencimento respeita documento, e conta prevista respeita a abertura. Categoria não alterada conserva seu snapshot mesmo se renomeada/inativada. Mudança de categoria valida o plano atual. Converter entre obrigação financeira e depreciação sem título continua exigindo cancelamento/novo registro; nunca cria ou remove pagamentos silenciosamente.

Pagamentos e estornos existentes não mudam. Corrigir conta/data/valor de um pagamento usa estorno e nova baixa; conta prevista só muda a previsão. Editar a base recorrente afeta apenas gerações posteriores; ocorrências existentes são independentes. Canceladas permanecem imutáveis. A edição geral é master; a permissão existente de reclassificação continua restrita a esse escopo.

## Baixa em lote
Exige operate_expenses, operate_finance e pay_titles. Seleção explícita das pendentes da página, até 100 por requisição; sem seleção implícita das demais páginas. Tela de conferência apresenta cada despesa/categoria/saldo, conta, data e soma. Baixa todo o saldo pendente, sem encargos; parcial, juros e descontos continuam na baixa individual.

Prévia assinada, vinculada ao usuário, conta, data, saldos e revisões, expira em 30 minutos. A confirmação roda uma transação para todo o lote e usa settle por título, com UUID determinístico por despesa/lote. Reenvio não duplica; alteração concorrente invalida o lote inteiro. Cada baixa conserva a categoria da despesa e produz seu próprio lançamento, permitindo estorno individual. Data futura mantém a política da ADR 0037: reserva principal, caixa somente na data.

## Verificação
Testes de edição, sincronismo da obrigação, pagamentos parciais/existentes, revisões, conflitos, rollback, permissões e proteção SQL. Lote cobre categorias distintas, residual parcial, futuro, reenvio e conflito no segundo título sem gravação parcial. Navegador percorre edição, seleção, prévia, confirmação e tela móvel.
