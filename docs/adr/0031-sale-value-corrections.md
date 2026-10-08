# ADR 0031 — Correção de valores de venda confirmada

Data: 08/10/2026. Estado: aceito.

O master pode corrigir produtos (valor total), desconto, fretes recebido/pago, taxas, DIFAL, comissão e outros custos de uma venda confirmada, sem cancelar ou importar novamente a NF. A correção exige motivo e revisão atual; chave idempotente impede repetição. SaleCorrection conserva antes/depois, autor e horário. Trigger PostgreSQL aceita apenas a alteração autorizada que corresponde ao registro imutável; bloqueios de itens, consumo, CMV e demais snapshots permanecem.

Receita alterada recalcula imposto automático pelos termos históricos da própria venda. Imposto manual e regras de recálculo retroativo existentes são preservados. Vendas com recebível histórico não podem alterar receita por este fluxo; taxas e frete pago continuam corrigíveis. Relatórios usam os valores corrigidos na competência original. Estoque e identidade fiscal não mudam.

Venda cancelada por engano continua pelo fluxo de recuperação (ADR 0028), agora destacado no topo. Depois de recuperada permite correções adicionais. A NF/série permanece única inclusive quando cancelada: não se exclui a identidade para forçar reimportação. Novas tentativas de cadastro orientam abrir a venda existente.

Consulta Bling passa a aceitar número/série. Número informado usa GET /nfe com numero, serie e tipo, sem filtros de data/situação/loja, valida identidade do detalhe e mantém critérios de elegibilidade. Notas sem loja externa são aceitas; uma consulta que não retorna a NF não comprova cancelamento. Nenhuma nota do banco real foi alterada automaticamente.

Campos monetários usam digitação por centavos, substituindo o conteúdo no primeiro dígito após foco. Quantidades, percentuais e datas não adotam máscara monetária. Colagem com separador decimal preserva a precisão permitida de custos unitários. Valores internos continuam Decimal, sem cálculo financeiro em float no navegador.
