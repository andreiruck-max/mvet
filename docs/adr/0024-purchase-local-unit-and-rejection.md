# ADR 0024 — Unidade local e rejeição de compras

Aceito em 29/09/2026 por solicitação do usuário; substitui a compatibilidade de unidades de compras do ADR 0023.

A unidade cadastrada no produto MVet prevalece. Quantidade e preço unitário externos são mantidos, sem conversão, fator de embalagem ou conciliação de siglas. Unidade externa permanece informativa. Selecionar o produto continua necessário para identificar o cadastro; não cria alias de unidade. Declaração de destinatário/finalidade normal e controles financeiros permanecem.

Notas sem compra vinculada podem ser rejeitadas e reabertas por operate_purchases. Rejeição remove das pendências sem efeitos financeiros/estoque ou alteração no Bling. Reconsulta preserva rejeição e identidade fiscal, impedindo reaparecimento. Compra vinculada usa cancelamento próprio. Operações atômicas, revisão otimista e auditoria.
